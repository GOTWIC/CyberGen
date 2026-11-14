// lifegen's Mass processors (LG0): see CityGenLifeProcessors.h.

#include "CityGenLifeProcessors.h"
#include "CityGenLifeTypes.h"
#include "Algo/Sort.h"
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

	/** cars_steam: the lowest point speed (cm/s) from `Dist` along a lane to `Look` cm on
	 *  (the points' speeds already brake before a bend: this is where the car is now). */
	float SpeedAhead(const FZoneGraphStorage& S, const TArray<float>& V, const int32 Lane,
	                 const float Dist, const float Look)
	{
		const FZoneLaneData& L = S.Lanes[Lane];
		float Out = 1e9f;
		for (int32 P = L.PointsBegin; P < L.PointsEnd; ++P)
		{
			const float Prog = S.LanePointProgressions[P];
			if (Prog + 1.f < Dist && P + 1 < L.PointsEnd && S.LanePointProgressions[P + 1] < Dist)
			{
				continue;
			}
			if (Prog > Dist + Look)
			{
				break;
			}
			if (V.IsValidIndex(P) && V[P] > 0.f)
			{
				Out = FMath::Min(Out, V[P]);
			}
		}
		return Out < 1e8f ? Out : 900.f;
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

	// --- LG3: the city's crowd ------------------------------------------------------------------

	/** Whether people may start crossing at signal window `Sig` now (`Grace` s after its end
	 *  for a group's followers, so a group is not cut in two by the hand starting to flash). */
	bool SignalOpen(const FCgLifeFrame& F, const int32 Sig, const float Grace)
	{
		const TArray<float>& W = *F.SignalWindows;
		if (!W.IsValidIndex(4 * Sig + 3))
		{
			return true;
		}
		const double Cycle = FMath::Max(1.0, (double)W[4 * Sig]);
		const float T = (float)FMath::Fmod(F.Time + (double)W[4 * Sig + 1], Cycle);
		return T >= W[4 * Sig + 2] && T < W[4 * Sig + 3] + Grace;
	}

	/** A person's speed on a walkway of `Kind` at its pace (cm/s). */
	float KindSpeed(const FCgLifeFrame& F, const uint8 Kind, const float Pace)
	{
		switch (Kind)
		{
		case CgKind::Stairs: return Pace * F.StairsShare;
		case CgKind::Escalator: return Pace * F.EscShare + F.EscAddCm;
		case CgKind::Elevator: return F.ElevatorCm;
		default: return Pace;
		}
	}

	/** A person's next walkway at a lane's end: one of its links of `Type` that is live,
	 *  weighted by its kind (elevators and skybridges seldom, paths less: most people keep to
	 *  the streets), not `Avoid` (back the way it came) unless that is the only one;
	 *  INDEX_NONE without one (it turns back). */
	int32 PickWalk(const FCgLifeFrame& F, const int32 Lane, const EZoneLaneLinkType Type,
	               const int32 Avoid, uint32& Seed)
	{
		const FZoneGraphStorage& S = *F.Storage;
		const FZoneLaneData& L = S.Lanes[Lane];
		int32 Cands[24];
		float Wts[24];
		int32 N = 0;
		float Tot = 0.f;
		bool bAvoided = false;
		for (int32 K = L.LinksBegin; K < L.LinksEnd && N < 24; ++K)
		{
			const FZoneLaneLinkData& Link = S.LaneLinks[K];
			const int32 To = Link.DestLaneIndex;
			if (Link.Type != Type || To < 0 || To >= F.WalkLanes || !(*F.InRegion)[To])
			{
				continue;
			}
			if (To == Avoid)
			{
				bAvoided = true;
				continue;
			}
			const uint8 Kd = (*F.LaneKind)[To];
			const float Wt = Kd == CgKind::Elevator ? 0.12f : (Kd == CgKind::Skybridge ? 0.4f : (Kd == CgKind::Path ? 0.6f : 1.f));
			Cands[N] = To;
			Wts[N] = Wt;
			Tot += Wt;
			++N;
		}
		if (N == 0)
		{
			return bAvoided ? Avoid : INDEX_NONE;
		}
		float X = (float)(Next(Seed) % 10000u) / 10000.f * Tot;
		for (int32 I = 0; I < N; ++I)
		{
			X -= Wts[I];
			if (X < 0.f)
			{
				return Cands[I];
			}
		}
		return Cands[N - 1];
	}

	void Place(FCgLifeFrame& F, const FCgLifeWalker& W, const uint8 Show)
	{
		if (F.WalkPos->IsValidIndex(W.Instance))
		{
			(*F.WalkPos)[W.Instance] = W.Pos;
			(*F.WalkYaw)[W.Instance] = W.Yaw;
			(*F.WalkState)[W.Instance] = Show;
		}
	}

	/** A person out of the city: its slot back in the pool. */
	void Free(FCgLifeFrame& F, FCgLifeWalker& W)
	{
		if (F.LaneHave->IsValidIndex(W.Lane))
		{
			--(*F.LaneHave)[W.Lane];
		}
		W.Active = 0;
		W.State = CgWalk::Walk;
		W.Door = INDEX_NONE;
		W.Pos = FVector::ZeroVector;
		Place(F, W, CgShow::Off);
		F.Freed->Add(W.Instance);
	}

	/** One person's step of `Dt` s (LG3). */
	void StepCity(FCgLifeFrame& F, FCgLifeWalker& W, const float Dt, const uint8 Tier)
	{
		const FZoneGraphStorage& S = *F.Storage;
		const TArray<float>& Len = *F.Lengths;
		// (through a door: out of it onto the walkway, or in at it and gone)
		if (W.State == CgWalk::Exit || W.State == CgWalk::Enter)
		{
			if (!F.DoorInside->IsValidIndex(W.Door))
			{
				Free(F, W);
				return;
			}
			const bool bOut = W.State == CgWalk::Exit;
			const FVector From = bOut ? (*F.DoorInside)[W.Door] : W.From;
			const FVector To = bOut ? (*F.DoorStreet)[W.Door] : (*F.DoorInside)[W.Door];
			const float Dur = FMath::Max(0.3f, (float)FVector::Dist(From, To) / FMath::Max(50.f, W.Speed));
			W.T += Dt;
			const float U = FMath::Clamp(W.T / Dur, 0.f, 1.f);
			W.Pos = FMath::Lerp(From, To, U) + FVector(0.f, 0.f, W.ZOff);
			const FVector D = To - From;
			if (D.SizeSquared2D() > 1.0)
			{
				W.Yaw = FMath::RadiansToDegrees(FMath::Atan2(D.Y, D.X));
			}
			if (U < 1.f)
			{
				Place(F, W, CgShow::Moving);
				return;
			}
			if (!bOut)
			{
				++F.Entered;
				Free(F, W);
				return;
			}
			++F.Exited;
			W.State = CgWalk::Walk;
			W.T = 0.f;
			W.Door = INDEX_NONE;
			W.Lat = 0.f;
		}
		if (!S.Lanes.IsValidIndex(W.Lane) || W.Lane >= F.WalkLanes)
		{
			Free(F, W);
			return;
		}
		bool bStill = false;
		if (W.State == CgWalk::Wait)
		{
			const int32 Sig = (*F.LaneSignal)[W.Lane];
			if (Sig < 0 || SignalOpen(F, Sig, W.Member > 0 ? 4.f : 0.f))
			{
				W.State = CgWalk::Walk;
				W.Crossed = 1;
			}
			else
			{
				bStill = true;
				++F.Waiting;
			}
		}
		const uint8 Kind = (*F.LaneKind)[W.Lane];
		if (W.State == CgWalk::Walk)
		{
			W.TripLeft -= Dt;
			const float V = KindSpeed(F, Kind, W.Speed) * (Kind == CgKind::Elevator ? 1.f : W.SpeedMul);
			bStill = V < 25.f;
			W.Dist += W.Dir * V * Dt;
			// (a signalized crosswalk: wait at its curb until people may start crossing, or
			// cross against it, more often where the district is dangerous)
			const int32 Sig = (*F.LaneSignal)[W.Lane];
			if (Sig >= 0 && !W.Crossed)
			{
				const float Hold = W.Dir > 0.f ? (*F.HoldA)[W.Lane] - W.HoldBack : (*F.HoldB)[W.Lane] + W.HoldBack;
				if (W.Dir > 0.f ? W.Dist >= Hold : W.Dist <= Hold)
				{
					const int32 Dd = (*F.LaneDistrict)[W.Lane];
					const float Danger = F.DistrictDanger->IsValidIndex(Dd) ? (*F.DistrictDanger)[Dd] : 0.5f;
					const float P = FMath::Lerp((float)F.Jaywalk.X, (float)F.Jaywalk.Y, Danger);
					if (SignalOpen(F, Sig, W.Member > 0 ? 4.f : 0.f))
					{
						W.Crossed = 1;
					}
					else if ((float)(Next(W.Seed) % 10000u) < P * 10000.f)
					{
						W.Crossed = 1;
						++F.Jaywalked;
					}
					else
					{
						W.Dist = Hold;
						W.State = CgWalk::Wait;
						bStill = true;
						++F.Waiting;
					}
				}
			}
			// (the trip's end: in at the next door ahead on its walkway)
			if (W.TripLeft <= 0.f && W.Door == INDEX_NONE && W.State == CgWalk::Walk)
			{
				const int32 A = (*F.LaneDoorStarts)[W.Lane];
				const int32 B = (*F.LaneDoorStarts)[W.Lane + 1];
				float Best = 1.0e9f;
				for (int32 K = A; K < B; ++K)
				{
					const float Ahead = ((*F.DoorDists)[K] - W.Dist) * W.Dir;
					if (Ahead >= 0.f && Ahead < Best)
					{
						Best = Ahead;
						W.Door = K;
					}
				}
			}
			if (W.Door != INDEX_NONE && W.State == CgWalk::Walk && ((*F.DoorDists)[W.Door] - W.Dist) * W.Dir <= 0.f)
			{
				W.State = CgWalk::Enter;
				W.T = 0.f;
				W.From = W.Pos;
				Place(F, W, CgShow::Moving);
				return;
			}
			// (a trip long over far from the view, where no door came: gone where nobody sees)
			if (W.TripLeft < -120.f && Tier >= 3)
			{
				Free(F, W);
				return;
			}
			for (int32 Guard = 0; Guard < 4; ++Guard)
			{
				const float L = Len[W.Lane];
				if (W.Dist >= 0.f && W.Dist <= L)
				{
					break;
				}
				const bool bEnd = W.Dist > L;
				const float Over = FMath::Min(bEnd ? W.Dist - L : -W.Dist, 200.f);
				const int32 To = PickWalk(F, W.Lane, bEnd ? EZoneLaneLinkType::Outgoing : EZoneLaneLinkType::Incoming, W.PrevLane, W.Seed);
				if (To == INDEX_NONE)
				{
					// (a dead end, or the edge of the live walkways: turn back)
					W.Dir = -W.Dir;
					W.Dist = bEnd ? FMath::Max(0.f, L - Over) : FMath::Min(L, Over);
					W.PrevLane = INDEX_NONE;
					W.Crossed = 0;
					continue;
				}
				const FZoneLaneData& Cur = S.Lanes[W.Lane];
				const FVector Here = S.LanePoints[bEnd ? Cur.PointsEnd - 1 : Cur.PointsBegin];
				const FZoneLaneData& Nx = S.Lanes[To];
				const bool bAtStart = FVector::DistSquared(Here, S.LanePoints[Nx.PointsBegin]) <=
					FVector::DistSquared(Here, S.LanePoints[Nx.PointsEnd - 1]);
				--(*F.LaneHave)[W.Lane];
				++(*F.LaneHave)[To];
				W.PrevLane = W.Lane;
				W.Lane = To;
				W.Dir = bAtStart ? 1.f : -1.f;
				W.Dist = bAtStart ? Over : Len[To] - Over;
				W.Crossed = 0;
				W.Door = INDEX_NONE;
			}
		}
		W.Dist = FMath::Clamp(W.Dist, 0.f, Len[W.Lane]);
		FZoneGraphLaneLocation Loc;
		if (!UE::ZoneGraph::Query::CalculateLocationAlongLane(S, W.Lane, W.Dist, Loc))
		{
			return;
		}
		// (keep to its side, out of the others' way and the player's; across at most 0.7 m/s)
		const FVector Right = FVector::CrossProduct(Loc.Up, Loc.Direction).GetSafeNormal();
		const float HW = 0.5f * (*F.Widths)[W.Lane];
		float Goal = W.Side * HW * W.Dir + W.Push;
		if (F.bPlayer)
		{
			const FVector Rel = F.Player - Loc.Position;
			const float Room = 0.6f * F.PlayerCm;
			// (in 3D: a pawn flying over them is no one to step aside from)
			if (Rel.SizeSquared() < FMath::Square(F.PlayerCm))
			{
				const float PL = (float)FVector::DotProduct(Rel, Right);
				if (FMath::Abs(Goal - PL) < Room)
				{
					Goal += (Goal >= PL ? 1.f : -1.f) * (Room - FMath::Abs(Goal - PL));
				}
			}
		}
		Goal = FMath::Clamp(Goal, -0.85f * HW, 0.85f * HW);
		W.Lat = FMath::FInterpConstantTo(W.Lat, Goal, Dt, 70.f);
		W.Pos = Loc.Position + Right * W.Lat + FVector(0.f, 0.f, W.ZOff);
		const FVector Fwd = Loc.Direction * W.Dir;
		if (Fwd.SizeSquared2D() > 1.0e-4)
		{
			W.Yaw = FMath::RadiansToDegrees(FMath::Atan2(Fwd.Y, Fwd.X));
		}
		Place(F, W, Kind == CgKind::Elevator ? CgShow::Hidden : (bStill ? CgShow::Still : CgShow::Moving));
	}
}

void UCityGenLifeWalkProcessor::ExecuteCity(FMassExecutionContext& Context)
{
	FCgLifeFrame& F = *Frame;
	const float Dt0 = FMath::Min(0.1f, Context.GetDeltaTimeSeconds());
	const double Avoid2 = FMath::Square((double)F.AvoidCm);
	const double Player2 = FMath::Square((double)F.PlayerCm);
	F.Waiting = 0;

	// (1) the avoidance: people near enough the view to see it, sorted by lane and distance
	// along it; each reacts to those ahead of it on its lane (and slows near the player)
	Near.Reset();
	Query.ForEachEntityChunk(Context, [&](FMassExecutionContext& Ctx)
	{
		const TArrayView<FCgLifeWalker> List = Ctx.GetMutableFragmentView<FCgLifeWalker>();
		for (int32 I = 0; I < Ctx.GetNumEntities(); ++I)
		{
			FCgLifeWalker& W = List[I];
			W.Push = 0.f;
			W.SpeedMul = 1.f;
			if (W.Active && W.State <= CgWalk::Wait && FVector::DistSquared(W.Pos, F.View) <= Avoid2)
			{
				Near.Add(&W);
				if (F.bPlayer && FVector::DistSquared(W.Pos, F.Player) < Player2)
				{
					const FVector Rel = F.Player - W.Pos;
					const FVector Fwd(FMath::Cos(FMath::DegreesToRadians(W.Yaw)), FMath::Sin(FMath::DegreesToRadians(W.Yaw)), 0.0);
					if (FVector::DotProduct(Rel, Fwd) > 0.0)
					{
						W.SpeedMul = 0.6f;
					}
				}
			}
		}
	});
	Algo::Sort(Near, [](const FCgLifeWalker* A, const FCgLifeWalker* B)
	{
		return A->Lane < B->Lane || (A->Lane == B->Lane && A->Dist < B->Dist);
	});
	const float Reach = F.ReachCm;
	const float Pers = F.PersonalCm;
	for (int32 A = 0; A < Near.Num(); ++A)
	{
		FCgLifeWalker& Me = *Near[A];
		auto Consider = [&](const FCgLifeWalker& O)
		{
			if (Me.Group != INDEX_NONE && O.Group == Me.Group)
			{
				return;
			}
			const float Along = (O.Dist - Me.Dist) * Me.Dir;
			if (Along <= 0.f || Along > Reach)
			{
				return;
			}
			const float DLat = O.Lat - Me.Lat;
			const float Room = 2.f * Pers - FMath::Abs(DLat);
			if (Room <= 0.f)
			{
				return;
			}
			const float Close = 1.f - Along / Reach;
			if (O.Dir == Me.Dir)
			{
				const bool bStopped = O.State == CgWalk::Wait;
				const float Ov = bStopped ? 0.f : O.Speed * O.SpeedMul;
				if (!bStopped && Ov >= Me.Speed * 0.97f)
				{
					return;
				}
				// (slower or stopped ahead: past it on its left, or the side with more room;
				// right behind it, slowing to its pace)
				const float Away = DLat > 5.f ? -1.f : (DLat < -5.f ? 1.f : -Me.Dir);
				Me.Push += Away * Room * Close;
				if (FMath::Abs(DLat) < Pers)
				{
					const float K = FMath::Clamp((Along - Pers) / FMath::Max(1.f, Reach - 2.f * Pers), 0.f, 1.f);
					Me.SpeedMul = FMath::Min(Me.SpeedMul, (Ov + (Me.Speed - Ov) * K) / FMath::Max(1.f, Me.Speed));
				}
			}
			else
			{
				// (face to face: each steps to its own right)
				Me.Push += Me.Dir * Room * Close;
			}
		};
		for (int32 B = A + 1; B < Near.Num() && Near[B]->Lane == Me.Lane && Near[B]->Dist - Me.Dist < Reach; ++B)
		{
			Consider(*Near[B]);
		}
		for (int32 B = A - 1; B >= 0 && Near[B]->Lane == Me.Lane && Me.Dist - Near[B]->Dist < Reach; --B)
		{
			Consider(*Near[B]);
		}
	}

	// (2) each person's step: the near and mid people every frame, the far every second, those
	// drawn by no tier every fourth (with the time they missed)
	Query.ForEachEntityChunk(Context, [&](FMassExecutionContext& Ctx)
	{
		const TArrayView<FCgLifeWalker> List = Ctx.GetMutableFragmentView<FCgLifeWalker>();
		for (int32 I = 0; I < Ctx.GetNumEntities(); ++I)
		{
			FCgLifeWalker& W = List[I];
			if (!W.Active)
			{
				continue;
			}
			const uint8 Tier = F.PersonTier && F.PersonTier->IsValidIndex(W.Instance) ? (*F.PersonTier)[W.Instance] : 0;
			const int32 Every = (Tier <= 1 || W.State >= CgWalk::Enter) ? 1 : (Tier == 2 ? 2 : 4);
			W.Pending += Dt0;
			if (Every > 1 && ((F.FrameNo + W.Instance) % Every) != 0)
			{
				continue;
			}
			const float Dt = FMath::Min(W.Pending, 0.4f);
			W.Pending = 0.f;
			CgLife::StepCity(F, W, Dt, Tier);
		}
	});
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
	if (Frame->bCity)
	{
		// (LG3: the city's crowd)
		ExecuteCity(Context);
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
			// (cars_steam: the lane's speed where the car is and a few meters on, its road's
			// class, a junction's, a bend's, braking before it; LG0's cruise without them)
			float Cruise = C.Cruise;
			if (Frame->PointVmax)
			{
				Cruise = C.Share * CgLife::SpeedAhead(S, *Frame->PointVmax, C.Lane, C.Dist, FMath::Max(400.f, C.Speed * 0.6f));
			}
			// (full speed with two gaps clear, stopped at one)
			const float Want = Cruise * FMath::Clamp((Ahead - Gap) / Gap, 0.f, 1.f);
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
			// (cars_steam: heading along the lane's tangent, interpolated between its points,
			// not the segment's: the lanes are smoothed curves, so the car turns as it moves)
			const FVector Hd = Loc.Tangent.IsNearlyZero() ? Loc.Direction : Loc.Tangent;
			C.Yaw = FMath::RadiansToDegrees(FMath::Atan2(Hd.Y, Hd.X));
			if (Frame->CarPos->IsValidIndex(C.Index))
			{
				(*Frame->CarPos)[C.Index] = C.Pos;
				(*Frame->CarYaw)[C.Index] = C.Yaw;
			}
		}
	});
}
