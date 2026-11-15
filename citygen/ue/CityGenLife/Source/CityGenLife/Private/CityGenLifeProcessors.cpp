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
	/** LG4: whether a person of its role may walk a walkway: a gang member only its turf's, a
	 *  patrol only the patrol walkways, everyone else any. */
	bool RoleMay(const FCgLifeFrame& F, const FCgLifeWalker& W, const int32 To)
	{
		if (W.Role == CgRole::Gang)
		{
			return F.LaneTurf && F.LaneTurf->IsValidIndex(To) && (*F.LaneTurf)[To] == W.Turf;
		}
		if (W.Role == CgRole::Police)
		{
			return F.LanePatrol && F.LanePatrol->IsValidIndex(To) && (*F.LanePatrol)[To];
		}
		return true;
	}

	int32 PickWalk(const FCgLifeFrame& F, const FCgLifeWalker& W, const int32 Lane, const EZoneLaneLinkType Type,
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
			if (Link.Type != Type || To < 0 || To >= F.WalkLanes || !(*F.InRegion)[To] || !RoleMay(F, W, To))
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

	// --- lifegen_people_fixes: turning ----------------------------------------------------------

	/** A person's yaw turned toward `Want` (deg) at most F.TurnDegS a second; a new person
	 *  faces it at once. */
	void TurnTo(const FCgLifeFrame& F, FCgLifeWalker& W, const float Want, const float Dt)
	{
		if (!W.Faced)
		{
			W.Yaw = Want;
			W.Faced = 1;
			return;
		}
		const float Step = F.TurnDegS * FMath::Max(Dt, 0.f);
		const float D = FMath::FindDeltaAngleDegrees(W.Yaw, Want);
		W.Yaw = FRotator::NormalizeAxis(W.Yaw + FMath::Clamp(D, -Step, Step));
	}

	/** A walkway lane's points in a walker's order (its first the one it walks from): the k-th
	 *  point and how far along it is (cm). */
	struct FWalkPath
	{
		const FZoneGraphStorage& S;
		int32 B = 0, E = 0;
		float Len = 0.f;
		bool bFwd = true;
		FWalkPath(const FZoneGraphStorage& InS, const int32 Lane, const float Dir)
			: S(InS)
		{
			const FZoneLaneData& L = S.Lanes[Lane];
			B = L.PointsBegin;
			E = L.PointsEnd;
			Len = S.LanePointProgressions[E - 1];
			bFwd = Dir > 0.f;
		}
		int32 Num() const { return E - B; }
		int32 Index(const int32 K) const { return bFwd ? B + K : E - 1 - K; }
		FVector P(const int32 K) const { return S.LanePoints[Index(K)]; }
		float At(const int32 K) const
		{
			const float Q = S.LanePointProgressions[Index(K)];
			return bFwd ? Q : Len - Q;
		}
	};

	/** How far along each leg a corner between headings D1 and D2 (unit) is rounded: at most
	 *  F.CornerCm and F.CornerLeg of the shorter leg, and so that it cuts the corner by at
	 *  most F.CornerCut of the half width `HW` (a quadratic curve over 2s cuts it by
	 *  s |D2 - D1| / 4); none on a straight run or a turn back. */
	float CornerS(const FCgLifeFrame& F, const FVector& D1, const float L1, const FVector& D2,
	              const float L2, const float HW)
	{
		const float Turn = (float)(D2 - D1).Size();
		if (Turn < 0.03f || FVector::DotProduct(D1, D2) < -0.85)
		{
			return 0.f;
		}
		return FMath::Max(0.f, FMath::Min3(F.CornerCm, F.CornerLeg * FMath::Min(L1, L2),
		                                   F.CornerCut * HW / (0.25f * Turn)));
	}

	/** The first leg (unit heading, length) and half width of the walkway a person goes on to
	 *  (W.Next); false without one. */
	bool NextLeg(const FCgLifeFrame& F, const FCgLifeWalker& W, FVector& D2, float& L2, float& HW2)
	{
		if (W.Next == INDEX_NONE || !F.Storage->Lanes.IsValidIndex(W.Next))
		{
			return false;
		}
		const FZoneGraphStorage& S = *F.Storage;
		const FZoneLaneData& L = S.Lanes[W.Next];
		if (L.PointsEnd - L.PointsBegin < 2)
		{
			return false;
		}
		const FVector A = S.LanePoints[W.NextAtStart ? L.PointsBegin : L.PointsEnd - 1];
		const FVector B = S.LanePoints[W.NextAtStart ? L.PointsBegin + 1 : L.PointsEnd - 2];
		L2 = (float)FVector::Dist(A, B);
		if (L2 < 1.f)
		{
			return false;
		}
		D2 = (B - A) / L2;
		HW2 = 0.5f * (*F.Widths)[W.Next];
		return true;
	}

	/** Where on its walkway's line a person is and which way it heads (unit, the walker's
	 *  way): the line's corners, between its stretches and between its walkway and the one
	 *  before or after it, rounded by a quadratic curve over CornerS each way, so its place
	 *  and heading change smoothly round them (no jump of its side offset, no snap of its
	 *  heading); the line itself elsewhere. */
	void PathAt(const FCgLifeFrame& F, const FCgLifeWalker& W, FVector& OutPos, FVector& OutHead)
	{
		const FZoneGraphStorage& S = *F.Storage;
		const FWalkPath P(S, W.Lane, W.Dir);
		const int32 N = P.Num();
		const float Wd = FMath::Clamp(W.Dir > 0.f ? W.Dist : P.Len - W.Dist, 0.f, P.Len);
		int32 K = 0;
		while (K + 2 < N && P.At(K + 1) <= Wd)
		{
			++K;
		}
		const FVector A = P.P(K);
		const FVector B = P.P(K + 1);
		const float Seg = FMath::Max(1.f, P.At(K + 1) - P.At(K));
		const FVector Dk = (B - A).GetSafeNormal();
		OutPos = A + Dk * FMath::Clamp(Wd - P.At(K), 0.f, Seg);
		OutHead = Dk;
		const float HW = 0.5f * (*F.Widths)[W.Lane];
		auto Round = [&](const FVector& V, const FVector& D1, const FVector& D2, const float Sc, const float U)
		{
			const FVector P0 = V - D1 * Sc;
			const FVector P2 = V + D2 * Sc;
			OutPos = P0 * FMath::Square(1.f - U) + V * (2.f * U * (1.f - U)) + P2 * FMath::Square(U);
			const FVector T = D1 * (1.f - U) + D2 * U;
			if (!T.IsNearlyZero(1.0e-3))
			{
				OutHead = T.GetSafeNormal();
			}
		};
		// (the corner it has just come round: its stretch's start)
		{
			FVector D1;
			float L1 = 0.f, HW1 = HW;
			bool bHave = false;
			if (K > 0)
			{
				D1 = (A - P.P(K - 1)).GetSafeNormal();
				L1 = P.At(K) - P.At(K - 1);
				bHave = true;
			}
			else if (W.bPrev)
			{
				D1 = FVector(W.PrevHead);
				L1 = W.PrevSegLen;
				HW1 = FMath::Min(HW, W.PrevHW);
				bHave = true;
			}
			const float Past = Wd - P.At(K);
			const float Sc = bHave ? CornerS(F, D1, L1, Dk, Seg, HW1) : 0.f;
			if (Sc > 1.f && Past < Sc)
			{
				Round(A, D1, Dk, Sc, 0.5f + 0.5f * Past / Sc);
				return;
			}
		}
		// (the corner ahead: its stretch's end)
		{
			FVector D2;
			float L2 = 0.f, HW2 = HW;
			bool bHave = false;
			if (K + 2 < N)
			{
				D2 = (P.P(K + 2) - B).GetSafeNormal();
				L2 = P.At(K + 2) - P.At(K + 1);
				bHave = true;
			}
			else
			{
				bHave = NextLeg(F, W, D2, L2, HW2);
				HW2 = FMath::Min(HW, HW2);
			}
			const float To = P.At(K + 1) - Wd;
			const float Sc = bHave ? CornerS(F, Dk, Seg, D2, L2, HW2) : 0.f;
			if (Sc > 1.f && To < Sc)
			{
				Round(B, Dk, D2, Sc, 0.5f - 0.5f * To / Sc);
			}
		}
	}

	void Place(FCgLifeFrame& F, const FCgLifeWalker& W, const uint8 Show)
	{
		if (F.WalkPos->IsValidIndex(W.Instance))
		{
			(*F.WalkPos)[W.Instance] = W.Pos;
			(*F.WalkYaw)[W.Instance] = W.Yaw;
			(*F.WalkState)[W.Instance] = Show;
			if (F.WalkAnim && F.WalkAnim->IsValidIndex(W.Instance))
			{
				(*F.WalkAnim)[W.Instance] = W.State == CgWalk::AtSlot ? W.Anim : (uint8)CgAnim::Walk;
			}
		}
	}

	/** LG4: a person's place slot let go (its claim freed). */
	void LetGo(FCgLifeFrame& F, FCgLifeWalker& W)
	{
		if (W.Slot != INDEX_NONE && F.Release)
		{
			F.Release(W.Slot, W.Point);
			++F.SlotsLeft;
		}
		W.Slot = INDEX_NONE;
		W.Point = INDEX_NONE;
	}

	/** A person out of the city: its slot back in the pool. */
	void Free(FCgLifeFrame& F, FCgLifeWalker& W)
	{
		LetGo(F, W);
		if (F.LaneHave->IsValidIndex(W.Lane))
		{
			--(*F.LaneHave)[W.Lane];
		}
		W.Active = 0;
		W.State = CgWalk::Walk;
		W.Door = INDEX_NONE;
		W.Visit = 0;
		W.Pos = FVector::ZeroVector;
		Place(F, W, CgShow::Off);
		F.Freed->Add(W.Instance);
	}

	/** LG4: a uniform draw in [0, 1) from a person's own stream. */
	float Unit(FCgLifeWalker& W)
	{
		return (float)(Next(W.Seed) % 10000u) / 10000.f;
	}

	/** LG4: whether a slot wants another user now: under its wanted users (the fraction by
	 *  chance), of the person's role (a gang spot its own turf's). */
	bool SlotWants(const FCgLifeFrame& F, FCgLifeWalker& W, const int32 S)
	{
		if (!(*F.SlotLive)[S] || (*F.SlotRole)[S] != W.Role)
		{
			return false;
		}
		if (W.Role == CgRole::Gang && (*F.SlotTurf)[S] != W.Turf)
		{
			return false;
		}
		const float Want = (*F.SlotWant)[S];
		const int32 Have = (*F.SlotUsers)[S];
		if ((float)Have >= FMath::CeilToFloat(Want))
		{
			return false;
		}
		return (float)Have + Unit(W) < Want;
	}

	/** LG4: a person goes to a slot's point it has claimed, from where it is. */
	void GoToSlot(FCgLifeWalker& W, const int32 S, const int32 Pt)
	{
		W.Slot = S;
		W.Point = Pt;
		W.State = CgWalk::ToSlot;
		W.From = W.Pos;
		W.T = 0.f;
	}

	/** LG4: a person to, at and back from a place slot; true while that is what it does this
	 *  step, false once it is back on its walkway's line (it walks on). */
	bool StepSlot(FCgLifeFrame& F, FCgLifeWalker& W, const float Dt)
	{
		const int32 S = W.Slot;
		const bool bValid = S != INDEX_NONE && F.SlotLive && F.SlotLive->IsValidIndex(S) &&
			F.PointPos->IsValidIndex(W.Point);
		if (W.State != CgWalk::FromSlot && (!bValid || !(*F.SlotLive)[S]))
		{
			// (its slot gone: back to its walkway)
			LetGo(F, W);
			W.State = CgWalk::FromSlot;
			W.From = W.Pos;
			W.T = 0.f;
		}
		if (W.State == CgWalk::ToSlot)
		{
			const FVector To = (*F.PointPos)[W.Point] + FVector(0.f, 0.f, W.ZOff);
			const float Dur = FMath::Max(0.3f, (float)FVector::Dist(W.From, To) / FMath::Max(50.f, W.Speed));
			W.T += Dt;
			const float U = FMath::Clamp(W.T / Dur, 0.f, 1.f);
			W.Pos = FMath::Lerp(W.From, To, U);
			const FVector D = To - W.From;
			if (D.SizeSquared2D() > 1.0)
			{
				TurnTo(F, W, FMath::RadiansToDegrees(FMath::Atan2(D.Y, D.X)), Dt);
			}
			if (U < 1.f)
			{
				Place(F, W, CgShow::Moving);
				return true;
			}
			W.State = CgWalk::AtSlot;
			W.Anim = (*F.SlotAnim)[S];
			const float A = (*F.SlotDwell)[2 * S];
			const float B = (*F.SlotDwell)[2 * S + 1];
			W.Dwell = FMath::Lerp(A, FMath::Max(A, B), Unit(W));
			if (F.Occupy)
			{
				F.Occupy(S, W.Point);
			}
			++F.SlotsTaken;
		}
		if (W.State == CgWalk::AtSlot)
		{
			W.Pos = (*F.PointPos)[W.Point] + FVector(0.f, 0.f, W.ZOff);
			TurnTo(F, W, (*F.PointYaw)[W.Point], Dt);
			W.Dwell -= Dt;
			if (W.Dwell > 0.f)
			{
				Place(F, W, CgShow::Still);
				return true;
			}
			// (done: a club's queue goes in at its door, everyone else back to its walkway)
			const int32 Door = (*F.SlotDoor)[S];
			LetGo(F, W);
			if (Door >= 0 && F.DoorInside->IsValidIndex(Door) &&
				(!F.DoorOpenNow || (*F.DoorOpenNow)[Door]))
			{
				W.State = CgWalk::Enter;
				W.Door = Door;
				W.Visit = 0;
				W.From = W.Pos;
				W.T = 0.f;
				Place(F, W, CgShow::Moving);
				return true;
			}
			W.State = CgWalk::FromSlot;
			W.From = W.Pos;
			W.T = 0.f;
		}
		// (back to where it left its walkway's line, on its own side)
		FVector At, Head;
		PathAt(F, W, At, Head);
		const FVector Right = FVector::CrossProduct(FVector::UpVector, Head * W.Dir).GetSafeNormal();
		const FVector To = At + Right * W.Lat + FVector(0.f, 0.f, W.ZOff);
		const float Dur = FMath::Max(0.3f, (float)FVector::Dist(W.From, To) / FMath::Max(50.f, W.Speed));
		W.T += Dt;
		const float U = FMath::Clamp(W.T / Dur, 0.f, 1.f);
		W.Pos = FMath::Lerp(W.From, To, U);
		const FVector D = To - W.From;
		if (D.SizeSquared2D() > 1.0)
		{
			TurnTo(F, W, FMath::RadiansToDegrees(FMath::Atan2(D.Y, D.X)), Dt);
		}
		if (U < 1.f)
		{
			Place(F, W, CgShow::Moving);
			return true;
		}
		W.State = CgWalk::Walk;
		W.T = 0.f;
		return false;
	}

	/** One person's step of `Dt` s (LG3). */
	void StepCity(FCgLifeFrame& F, FCgLifeWalker& W, const float Dt, const uint8 Tier)
	{
		const FZoneGraphStorage& S = *F.Storage;
		const TArray<float>& Len = *F.Lengths;
		// (LG4: in a shop on a visit, not drawn; then out of its door again)
		if (W.State == CgWalk::Inside)
		{
			W.Dwell -= Dt;
			if (W.Dwell > 0.f && F.DoorInside->IsValidIndex(W.Door))
			{
				Place(F, W, CgShow::Hidden);
				return;
			}
			W.State = CgWalk::Exit;
			W.T = 0.f;
			W.Visit = 0;
		}
		// (LG4: to, at and back from a place slot)
		if (W.State == CgWalk::ToSlot || W.State == CgWalk::AtSlot || W.State == CgWalk::FromSlot)
		{
			if (!S.Lanes.IsValidIndex(W.Lane) || W.Lane >= F.WalkLanes)
			{
				Free(F, W);
				return;
			}
			if (StepSlot(F, W, Dt))
			{
				return;
			}
		}
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
				TurnTo(F, W, FMath::RadiansToDegrees(FMath::Atan2(D.Y, D.X)), Dt);
			}
			if (U < 1.f)
			{
				Place(F, W, CgShow::Moving);
				return;
			}
			if (!bOut)
			{
				if (W.Visit && F.DoorDwell && F.DoorDwell->IsValidIndex(2 * W.Door + 1))
				{
					// (LG4: in on a visit: out again after it)
					const float A = (*F.DoorDwell)[2 * W.Door];
					const float B = (*F.DoorDwell)[2 * W.Door + 1];
					W.State = CgWalk::Inside;
					W.Dwell = FMath::Lerp(A, FMath::Max(A, B), Unit(W));
					++F.Visits;
					Place(F, W, CgShow::Hidden);
					return;
				}
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
			const float DistBefore = W.Dist;
			W.Dist += W.Dir * V * Dt;
			// (LG4: a place slot passed on its walkway that wants a user: claimed and gone to;
			// an open shop's door passed: in for a visit, by its chance; crowd groups keep
			// together, a gang's members break off)
			if (F.bPlaces && W.Door == INDEX_NONE && W.Lane < F.WalkLanes &&
				(W.Group == INDEX_NONE || W.Role == CgRole::Gang))
			{
				const float Lo = FMath::Min(DistBefore, W.Dist);
				const float Hi = FMath::Max(DistBefore, W.Dist);
				if (F.LaneSlotStarts && F.LaneSlotStarts->IsValidIndex(W.Lane + 1))
				{
					for (int32 K = (*F.LaneSlotStarts)[W.Lane]; K < (*F.LaneSlotStarts)[W.Lane + 1]; ++K)
					{
						const int32 Sl = (*F.LaneSlots)[K];
						const float D = (*F.SlotDist)[Sl];
						if (D < Lo || D > Hi || Sl == W.PassedSlot)
						{
							continue;
						}
						W.PassedSlot = Sl;
						if (!SlotWants(F, W, Sl))
						{
							continue;
						}
						const int32 Pt = F.Claim ? F.Claim(Sl, W.Instance) : INDEX_NONE;
						if (Pt != INDEX_NONE)
						{
							GoToSlot(W, Sl, Pt);
							Place(F, W, CgShow::Moving);
							return;
						}
					}
				}
				if (F.DoorVisitNow && W.Role == CgRole::Crowd && W.Group == INDEX_NONE && W.TripLeft > 0.f)
				{
					for (int32 K = (*F.LaneDoorStarts)[W.Lane]; K < (*F.LaneDoorStarts)[W.Lane + 1]; ++K)
					{
						const float D = (*F.DoorDists)[K];
						if (D <= Lo || D > Hi || !(*F.DoorOpenNow)[K] || (*F.DoorDwell)[2 * K + 1] <= 0.f)
						{
							continue;
						}
						if (Unit(W) < (*F.DoorVisitNow)[K])
						{
							W.State = CgWalk::Enter;
							W.Door = K;
							W.Visit = 1;
							W.From = W.Pos;
							W.T = 0.f;
							Place(F, W, CgShow::Moving);
							return;
						}
					}
				}
			}
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
				for (int32 K = A; K < B && W.Role != CgRole::Gang; ++K)
				{
					// (LG4: an open door only; a patrol back in at its station's)
					if ((F.DoorOpenNow && !(*F.DoorOpenNow)[K]) ||
						(W.Role == CgRole::Police && (!F.DoorPolice || !(*F.DoorPolice)[K])))
					{
						continue;
					}
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
				// (the walkway chosen as it neared the end, if it is still live; else one now)
				const bool bChosen = W.Next != INDEX_NONE && W.Next < F.WalkLanes && (*F.InRegion)[W.Next];
				const int32 To = bChosen ? W.Next : PickWalk(F, W, W.Lane, bEnd ? EZoneLaneLinkType::Outgoing : EZoneLaneLinkType::Incoming, W.PrevLane, W.Seed);
				W.Next = INDEX_NONE;
				if (To == INDEX_NONE)
				{
					// (a dead end, or the edge of the live walkways: turn back, turning on the
					// spot: its side offset is the lane's, so it stays where it is)
					W.Dir = -W.Dir;
					W.Dist = bEnd ? FMath::Max(0.f, L - Over) : FMath::Min(L, Over);
					W.PrevLane = INDEX_NONE;
					W.Crossed = 0;
					W.bPrev = 0;
					continue;
				}
				const FZoneLaneData& Cur = S.Lanes[W.Lane];
				const FVector Here = S.LanePoints[bEnd ? Cur.PointsEnd - 1 : Cur.PointsBegin];
				const FZoneLaneData& Nx = S.Lanes[To];
				const bool bAtStart = FVector::DistSquared(Here, S.LanePoints[Nx.PointsBegin]) <=
					FVector::DistSquared(Here, S.LanePoints[Nx.PointsEnd - 1]);
				// (the heading it leaves this walkway on, for the corner into the next; its side
				// offset kept on the walker's own right, so it does not jump across)
				{
					const FVector Last = S.LanePoints[bEnd ? Cur.PointsEnd - 2 : Cur.PointsBegin + 1];
					const FVector Leg = Here - Last;
					W.PrevSegLen = (float)Leg.Size();
					W.PrevHead = FVector3f(Leg.GetSafeNormal());
					W.PrevHW = 0.5f * (*F.Widths)[W.Lane];
					W.bPrev = W.PrevSegLen > 1.f ? 1 : 0;
				}
				const float NewDir = bAtStart ? 1.f : -1.f;
				W.Lat *= W.Dir * NewDir;
				--(*F.LaneHave)[W.Lane];
				++(*F.LaneHave)[To];
				W.PrevLane = W.Lane;
				W.Lane = To;
				W.Dir = NewDir;
				W.Dist = bAtStart ? Over : Len[To] - Over;
				W.Crossed = 0;
				W.Door = INDEX_NONE;
			}
			// (nearing its walkway's end: the next one chosen now, so it rounds the corner into
			// it rather than turning on the spot)
			if (W.Next == INDEX_NONE && (W.Dir > 0.f ? Len[W.Lane] - W.Dist : W.Dist) < F.CornerCm + 50.f)
			{
				const bool bEnd = W.Dir > 0.f;
				W.Next = PickWalk(F, W, W.Lane, bEnd ? EZoneLaneLinkType::Outgoing : EZoneLaneLinkType::Incoming, W.PrevLane, W.Seed);
				if (W.Next != INDEX_NONE)
				{
					const FZoneLaneData& Cur = S.Lanes[W.Lane];
					const FVector Here = S.LanePoints[bEnd ? Cur.PointsEnd - 1 : Cur.PointsBegin];
					const FZoneLaneData& Nx = S.Lanes[W.Next];
					W.NextAtStart = FVector::DistSquared(Here, S.LanePoints[Nx.PointsBegin]) <=
						FVector::DistSquared(Here, S.LanePoints[Nx.PointsEnd - 1]) ? 1 : 0;
				}
			}
		}
		W.Dist = FMath::Clamp(W.Dist, 0.f, Len[W.Lane]);
		if (S.Lanes[W.Lane].PointsEnd - S.Lanes[W.Lane].PointsBegin < 2)
		{
			return;
		}
		// (lifegen_people_fixes: on its walkway's line with the corners rounded, its heading
		// the curve's, so it turns as it walks: no snap of its heading, no jump of its side)
		FVector At, Head;
		PathAt(F, W, At, Head);
		// (keep to its side, out of the others' way and the player's; across at most 0.7 m/s;
		// the side offset is on the lane's own right, the walker's right times its direction)
		const FVector Right = FVector::CrossProduct(FVector::UpVector, Head * W.Dir).GetSafeNormal();
		const float HW = 0.5f * (*F.Widths)[W.Lane];
		float Goal = W.Side * HW * W.Dir + W.Push;
		if (F.bPlayer)
		{
			const FVector Rel = F.Player - At;
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
		const float Lat0 = W.Lat;
		W.Lat = FMath::FInterpConstantTo(W.Lat, Goal, Dt, 70.f);
		W.Pos = At + Right * W.Lat + FVector(0.f, 0.f, W.ZOff);
		// (facing where it goes: along the walkway, and toward the side it is stepping to; turned
		// at most F.TurnDegS a second)
		FVector Fwd = Head;
		if (!bStill && Dt > 1.0e-4f)
		{
			const float V = KindSpeed(F, Kind, W.Speed) * W.SpeedMul;
			Fwd = Head * V + Right * ((W.Lat - Lat0) / Dt);
		}
		if (Fwd.SizeSquared2D() > 1.0e-4)
		{
			TurnTo(F, W, FMath::RadiansToDegrees(FMath::Atan2(Fwd.Y, Fwd.X)), Dt);
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
			// (LG4: someone sitting, standing at a slot or inside a shop far off as seldom as a
			// far walker; going through a door or to and from a slot every frame)
			const bool bMoving = W.State == CgWalk::Enter || W.State == CgWalk::Exit ||
				W.State == CgWalk::ToSlot || W.State == CgWalk::FromSlot;
			const int32 Every = (Tier <= 1 || bMoving) ? 1 : (Tier == 2 ? 2 : 4);
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
	if (Frame && Frame->Storage && Frame->bTraffic)
	{
		// (LG5: the city's traffic)
		ExecuteTraffic(Context);
		return;
	}
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
