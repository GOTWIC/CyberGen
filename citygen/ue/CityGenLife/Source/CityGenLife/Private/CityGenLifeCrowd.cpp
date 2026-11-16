// lifegen's city crowd (LG3): see CityGenLifeActor.h ("LG3: the city's crowd") and
// docs/unreal_export.md ("From LG3: crowds on the streets").
//
// The whole walkway graph is ZoneGraph lanes; only the walkways within LiveM of the view are
// live. Every LiveStep s (UpdateLive) the live set is measured again: a walkway coming alive
// (at LiveM, past the far tier's draw distance, so out of sight) gets its people at the hour
// (the plan's people per band times its district's day) times the scale that keeps the live
// people within the pool; a walkway going (past LiveM and a margin) loses its people; a
// person walking toward a walkway that is not live turns back there, also out of sight. Doors
// on the live walkways send people out at the plan's rates (more while the live people are
// under their number); a person whose trip is over goes in at the next door ahead of it.
// Every person is a slot of a fixed pool (Mass entities made once): no entity is made or
// destroyed while the game runs.

#include "CityGenLifeActor.h"
#include "CityGenLifeTypes.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/World.h"
#include "MassEntityManager.h"
#include "MassEntitySubsystem.h"
#include "ZoneGraphData.h"
#include "ZoneGraphQuery.h"
#include "ZoneGraphTypes.h"

namespace
{
	constexpr float LiveStep = 0.25f;     // s between live updates
	constexpr float LiveMarginM = 40.f;   // a live walkway goes this far past LiveM
	constexpr float PoolFill = 0.92f;     // the live people at most this share of the pool
	constexpr float InsideM = 0.6f;       // a door's inside point past its threshold

	FVector Ue(const float X, const float Y, const float Z)
	{
		return FVector(X * 100.0, -Y * 100.0, Z * 100.0);
	}

	int32 BandOf(const int32 Hour)
	{
		const int32 H = ((Hour % 24) + 24) % 24;
		return H < 6 ? 0 : (H < 10 ? 1 : (H < 16 ? 2 : (H < 20 ? 3 : 4)));
	}

	uint32 MixU(uint32 X)
	{
		X ^= X >> 16; X *= 0x7feb352du; X ^= X >> 15; X *= 0x846ca68bu; X ^= X >> 16;
		return X;
	}
}

float ACityGenLife::Want(const int32 Lane) const
{
	const int32 B = BandOf(Hour);
	const int32 D = LaneDistrictArr.IsValidIndex(Lane) ? LaneDistrictArr[Lane] : INDEX_NONE;
	const int32 H = ((Hour % 24) + 24) % 24;
	const float Shape = (D >= 0 && DistrictShape.IsValidIndex(24 * D + H)) ? DistrictShape[24 * D + H] : 1.f;
	return WalkPeople.IsValidIndex(5 * Lane + B) ? WalkPeople[5 * Lane + B] * Shape * CrowdScale : 0.f;
}

int32 ACityGenLife::GroupSize(FRandomStream& Rng) const
{
	float Tot = 0.f;
	for (const float S : GroupShares)
	{
		Tot += S;
	}
	if (Tot <= 0.f)
	{
		return 1;
	}
	float X = Rng.FRand() * Tot;
	for (int32 K = 0; K < GroupShares.Num(); ++K)
	{
		X -= GroupShares[K];
		if (X < 0.f)
		{
			return K + 1;
		}
	}
	return GroupShares.Num();
}

void ACityGenLife::BuildCrowd()
{
	const FZoneGraphStorage& S = Lanes->GetStorage();
	const int32 N = WalkLaneCount;
	LaneKindArr.SetNumZeroed(N);
	LaneSignalArr.Init(INDEX_NONE, N);
	LaneDistrictArr.Init(INDEX_NONE, N);
	HoldA.SetNumZeroed(N);
	HoldB.SetNumZeroed(N);
	LaneMid.SetNum(N);
	LaneHalf.SetNumZeroed(N);
	LaneHave.Init(0, WalkLaneCount + DriveLaneCount);
	const int32 NumWindows = SignalWindows.Num() / 4;
	const int32 NumDistricts = DistrictDanger.Num();
	for (int32 I = 0; I < N; ++I)
	{
		LaneKindArr[I] = WalkKinds.IsValidIndex(I) ? WalkKinds[I] : (uint8)3;
		const int32 Sg = WalkSignal.IsValidIndex(I) ? WalkSignal[I] : INDEX_NONE;
		LaneSignalArr[I] = (Sg >= 0 && Sg < NumWindows) ? Sg : INDEX_NONE;
		const int32 D = WalkDistrict.IsValidIndex(I) ? WalkDistrict[I] : INDEX_NONE;
		LaneDistrictArr[I] = (D >= 0 && D < NumDistricts) ? D : INDEX_NONE;
		const FZoneLaneData& L = S.Lanes[I];
		FBox Box(ForceInit);
		for (int32 P = L.PointsBegin; P < L.PointsEnd; ++P)
		{
			Box += S.LanePoints[P];
		}
		LaneMid[I] = Box.GetCenter();
		LaneHalf[I] = (float)Box.GetExtent().Size();
		// (a crosswalk's curbs: its second point walked forward, its last but one back; the
		// walkway runs from a corner to the curb, across, and on to the far corner)
		const int32 Np = L.PointsEnd - L.PointsBegin;
		const float Len = Lengths[I];
		HoldA[I] = Np >= 4 ? S.LanePointProgressions[L.PointsBegin + 1] : FMath::Min(100.f, Len / 3.f);
		HoldB[I] = Np >= 4 ? S.LanePointProgressions[L.PointsEnd - 2] : FMath::Max(Len - 100.f, 2.f * Len / 3.f);
		InRegion[I] = 0;
	}
	// (the doors by walkway lane and distance along it; where each meets its walkway and its
	// point just inside)
	const int32 ND = FMath::Min3(DoorLanes.Num(), DoorDistsM.Num(), DoorPoints.Num() / 3);
	TArray<int32> Order;
	for (int32 K = 0; K < ND; ++K)
	{
		if (DoorLanes[K] >= 0 && DoorLanes[K] < N)
		{
			Order.Add(K);
		}
	}
	Order.Sort([this](const int32 A, const int32 B)
	{
		return DoorLanes[A] < DoorLanes[B] || (DoorLanes[A] == DoorLanes[B] && DoorDistsM[A] < DoorDistsM[B]);
	});
	DoorDists.Reset();
	DoorStreet.Reset();
	DoorInside.Reset();
	DoorLive.Reset();
	TArray<int32> DoorLaneS;
	TArray<float> DoorRateS;
	LaneDoorStarts.Init(0, N + 1);
	// (LG4: the doors' hours, visits, stations and rates by the hour, in the same order)
	DoorSortedOf.Init(INDEX_NONE, ND);
	DoorRatesHSorted.Reset();
	DoorOpenSorted.Reset();
	DoorVisitSorted.Reset();
	DoorDwellSorted.Reset();
	DoorPoliceSorted.Reset();
	const bool bH = DoorRatesH.Num() >= 24 * ND && ND > 0;
	for (const int32 K : Order)
	{
		DoorSortedOf[K] = DoorDists.Num();
		for (int32 H = 0; H < 24 && bH; ++H)
		{
			DoorRatesHSorted.Add(FMath::Max(0.f, DoorRatesH[24 * K + H]));
		}
		DoorOpenSorted.Add(DoorOpen.IsValidIndex(K) ? DoorOpen[K] : 0xFFFFFF);
		for (int32 B = 0; B < 5; ++B)
		{
			DoorVisitSorted.Add(DoorVisit.IsValidIndex(5 * K + B) ? DoorVisit[5 * K + B] : 0.f);
		}
		DoorDwellSorted.Add(DoorDwell.IsValidIndex(2 * K) ? DoorDwell[2 * K] : 0.f);
		DoorDwellSorted.Add(DoorDwell.IsValidIndex(2 * K + 1) ? DoorDwell[2 * K + 1] : 0.f);
		DoorPoliceSorted.Add(DoorPolice.IsValidIndex(K) ? DoorPolice[K] : 0);
		const int32 Ln = DoorLanes[K];
		const float D = FMath::Clamp(100.f * DoorDistsM[K], 0.f, Lengths[Ln]);
		FZoneGraphLaneLocation Loc;
		UE::ZoneGraph::Query::CalculateLocationAlongLane(S, Ln, D, Loc);
		const FVector Door = Ue(DoorPoints[3 * K], DoorPoints[3 * K + 1], DoorPoints[3 * K + 2]);
		FVector In = Door - Loc.Position;
		In.Z = 0.0;
		In = In.GetSafeNormal() * (100.0 * InsideM);
		DoorDists.Add(D);
		DoorStreet.Add(Loc.Position);
		DoorInside.Add(Door + In);
		DoorLaneS.Add(Ln);
		DoorRateS.Add(DoorRates.IsValidIndex(K) ? FMath::Max(0.f, DoorRates[K]) : 1.f);
		++LaneDoorStarts[Ln + 1];
	}
	for (int32 I = 0; I < N; ++I)
	{
		LaneDoorStarts[I + 1] += LaneDoorStarts[I];
	}
	DoorLanesSorted = MoveTemp(DoorLaneS);
	DoorRatesSorted = MoveTemp(DoorRateS);

	Frame.bCity = true;
	Frame.LaneKind = &LaneKindArr;
	Frame.LaneSignal = &LaneSignalArr;
	Frame.SignalWindows = &SignalWindows;
	Frame.HoldA = &HoldA;
	Frame.HoldB = &HoldB;
	Frame.LaneDistrict = &LaneDistrictArr;
	Frame.DistrictDanger = &DistrictDanger;
	Frame.LaneDoorStarts = &LaneDoorStarts;
	Frame.DoorDists = &DoorDists;
	Frame.DoorStreet = &DoorStreet;
	Frame.DoorInside = &DoorInside;
	Frame.LaneHave = &LaneHave;
	Frame.PersonTier = &PersonTier;
	Frame.WalkState = &WalkState;
	Frame.Freed = &Freed;
	Frame.ReachCm = 100.f * ReachM;
	Frame.PersonalCm = 100.f * PersonalM;
	Frame.PlayerCm = 100.f * PlayerM;
	Frame.AvoidCm = 100.f * AvoidM;
	Frame.StairsShare = StairsShare;
	Frame.EscShare = (float)Escalator.X;
	Frame.EscAddCm = 100.f * (float)Escalator.Y;
	Frame.ElevatorCm = 100.f * ElevatorMS;
	Frame.Jaywalk = Jaywalk;
	Frame.TurnDegS = TurnDegS;
	Frame.CornerCm = 100.f * CornerM;
	if (IsPlaces())
	{
		// (LG4: life at places)
		BuildPlaces();
	}
}

void ACityGenLife::SpawnPool()
{
	// (every person a slot of the pool: People Mass entities made now, free until a walkway
	// round the view comes alive or a door sends them out)
	UMassEntitySubsystem* Sub = GetWorld()->GetSubsystem<UMassEntitySubsystem>();
	FMassEntityManager& EM = Sub->GetMutableEntityManager();
	const int32 NP = FMath::Max(0, People);
	WalkPos.Init(FVector::ZeroVector, NP);
	WalkYaw.SetNumZeroed(NP);
	WalkState.Init(CgShow::Off, NP);
	PersonStill.Init(0, NP);
	FreeSlots.Reset();
	Freed.Reset();
	ActiveNow = 0;
	if (NP)
	{
		const FMassArchetypeHandle Arch = EM.CreateArchetype({FCgLifeWalker::StaticStruct()});
		TArray<FMassEntityHandle> Hs;
		EM.BatchCreateEntities(Arch, NP, Hs);
		for (int32 K = 0; K < Hs.Num(); ++K)
		{
			FCgLifeWalker& W = EM.GetFragmentDataChecked<FCgLifeWalker>(Hs[K]);
			W = FCgLifeWalker();
			W.Active = 0;
			W.Instance = K;
		}
		Entities.Append(Hs);
		// (LG4: the slots the plan keeps for gang members and police in lists of their own)
		FreeGang.Reset();
		FreePolice.Reset();
		GangActive = PoliceActive = 0;
		for (int32 K = NP - 1; K >= 0; --K)
		{
			const uint8 PRole = PersonRole.IsValidIndex(K) && IsPlaces() ? PersonRole[K] : (uint8)CgRole::Crowd;
			(PRole == CgRole::Gang ? FreeGang : (PRole == CgRole::Police ? FreePolice : FreeSlots)).Add(K);
		}
		CrowdPoolN = FreeSlots.Num();
		GangPoolN = FreeGang.Num();
		PolicePoolN = FreePolice.Num();
	}
	for (int32 I = 0; I < LaneHave.Num(); ++I)
	{
		LaneHave[I] = 0;
	}
	for (int32 I = 0; I < WalkLaneCount; ++I)
	{
		InRegion[I] = 0;
	}
	CrowdRng.Initialize((int32)(MixU(GetTypeHash(City) ^ GetTypeHash(PlanHash)) & 0x7fffffff));
	LiveClock = LiveStep;          // (the first tick fills the live walkways)
	LastLiveView = FVector(1.0e12);
	DoorAcc = 0.f;
}

int32 ACityGenLife::SpawnGroup(const int32 Lane, const float Dist, const float Dir, const int32 Size, const int32 Door, FRandomStream& Rng,
	const uint8 PRole, const int32 Turf, TArray<int32>* OutSlots)
{
	// (LG4: a gang's members and police from their own slots of the pool)
	TArray<int32>& Free = PRole == CgRole::Gang ? FreeGang : (PRole == CgRole::Police ? FreePolice : FreeSlots);
	if (!Entities.Num() || Free.Num() == 0 || !InRegion.IsValidIndex(Lane))
	{
		return 0;
	}
	FMassEntityManager& EM = GetWorld()->GetSubsystem<UMassEntitySubsystem>()->GetMutableEntityManager();
	TArray<int32, TInlineAllocator<8>> Slots;
	float Pace = 1.0e9f;
	const int32 D0 = LaneDistrictArr.IsValidIndex(Lane) ? LaneDistrictArr[Lane] : INDEX_NONE;
	for (int32 K = 0; K < Size && Free.Num(); ++K)
	{
		// (LG2: a slot whose look is of a group the district wears, drawn by its people)
		const int32 Slot = PRole == CgRole::Crowd ? TakeSlot(D0, Rng) : Free.Pop(EAllowShrinking::No);
		Slots.Add(Slot);
		Pace = FMath::Min(Pace, 100.f * (PersonPace.IsValidIndex(Slot) ? PersonPace[Slot] : 1.35f));
	}
	if (OutSlots)
	{
		OutSlots->Append(Slots);
	}
	const int32 Group = Slots.Num() > 1 ? ++GroupCounter : INDEX_NONE;
	const uint32 Seed = Rng.GetUnsignedInt() | 1u;
	// (a gang member is out on its turf for good; a patrol a while, then back in at its station)
	const float Trip = PRole == CgRole::Gang ? 1.0e9f :
		(PRole == CgRole::Police ? TripS * (1.f + 2.f * Rng.FRand()) : TripS * (0.25f + 1.5f * Rng.FRand()));
	// (a patrol at a constable's pace)
	if (PRole == CgRole::Police)
	{
		Pace = FMath::Min(Pace, 115.f);
	}
	const float HW = FMath::Max(50.f, 0.5f * Widths[Lane]);
	// (most keep right, some left; a group walks in pairs, side by side, one pair behind
	// another)
	const float Side0 = (Rng.FRand() < 0.75f ? 1.f : -1.f) * FMath::Lerp(0.2f, 0.65f, Rng.FRand());
	const float Across = FMath::Min(0.8f, 60.f / HW);
	const int32 D = LaneDistrictArr.IsValidIndex(Lane) ? LaneDistrictArr[Lane] : INDEX_NONE;
	for (int32 M = 0; M < Slots.Num(); ++M)
	{
		const int32 Slot = Slots[M];
		FCgLifeWalker& W = EM.GetFragmentDataChecked<FCgLifeWalker>(Entities[Slot]);
		W = FCgLifeWalker();
		W.Active = 1;
		W.Instance = Slot;
		W.Lane = Lane;
		W.Dir = Dir >= 0.f ? 1.f : -1.f;
		const float Back = (Door >= 0 ? 0.f : (float)(M / 2) * 100.f * GroupGapM);
		W.Dist = FMath::Clamp(Dist - W.Dir * Back, 0.f, Lengths[Lane]);
		W.Side = FMath::Clamp(Side0 - ((M % 2) ? FMath::Sign(Side0) * Across : 0.f), -0.85f, 0.85f);
		W.Lat = W.Side * HW * W.Dir;
		W.Speed = Pace;
		W.Seed = Seed;
		W.Group = Group;
		W.Member = (uint8)M;
		W.TripLeft = Trip;
		W.HoldBack = 30.f + (float)(MixU((uint32)Slot + 7u) % 120u);
		W.Role = PRole;
		W.Turf = Turf;
		GangActive += PRole == CgRole::Gang ? 1 : 0;
		PoliceActive += PRole == CgRole::Police ? 1 : 0;
		if (Door >= 0)
		{
			// (out of its door one after another)
			W.State = CgWalk::Exit;
			W.Door = Door;
			W.T = -0.9f * (float)M;
		}
		if (LaneHave.IsValidIndex(Lane))
		{
			++LaneHave[Lane];
		}
		WalkState[Slot] = CgShow::Off;
		WalkPos[Slot] = FVector::ZeroVector;
		// (the clothes' color: a color of the district it comes out in; LG2: three, one per
		// dye channel, of its look's group in this district, and its wear)
		if (PRole == CgRole::Gang && TurfFaction.IsValidIndex(Turf) && FactionColors > 0)
		{
			// (LG4: a gang member in its faction's colors)
			DressFaction(Slot, TurfFaction[Turf], Rng);
		}
		else if (D >= 0 && OutfitColors > 0 && PersonGroup.IsValidIndex(Slot))
		{
			DressSlot(Slot, D, Rng);
		}
		else if (D >= 0 && PersonTintIndex.IsValidIndex(Slot) && PaletteSize > 0)
		{
			const int32 C = 3 * (D * PaletteSize + (PersonTintIndex[Slot] % PaletteSize));
			if (DistrictPalettes.IsValidIndex(C + 2))
			{
				PersonTint.SetNumZeroed(FMath::Max(PersonTint.Num(), 3 * People));
				PersonTint[3 * Slot] = DistrictPalettes[C];
				PersonTint[3 * Slot + 1] = DistrictPalettes[C + 1];
				PersonTint[3 * Slot + 2] = DistrictPalettes[C + 2];
			}
		}
		PersonStill[Slot] = 0;
		if (WalkAnimG.IsValidIndex(Slot))
		{
			WalkAnimG[Slot] = CgAnim::Walk;
		}
		ApplyLook(Slot, false);
		++ActiveNow;
		++Spawned;
	}
	return Slots.Num();
}

void ACityGenLife::FreeRole(const int32 Slot)
{
	// (LG4: a slot back in its role's list)
	const uint8 PRole = PersonRole.IsValidIndex(Slot) && IsPlaces() ? PersonRole[Slot] : (uint8)CgRole::Crowd;
	if (PRole == CgRole::Gang)
	{
		FreeGang.Add(Slot);
		--GangActive;
	}
	else if (PRole == CgRole::Police)
	{
		FreePolice.Add(Slot);
		--PoliceActive;
	}
	else
	{
		FreeSlots.Add(Slot);
	}
}

int32 ACityGenLife::TakeSlot(const int32 D, FRandomStream& Rng)
{
	const int32 G = OutfitGroupCount;
	if (D >= 0 && G > 0 && PersonGroup.Num() && DistrictGroups.IsValidIndex(D * G + G - 1))
	{
		float X = Rng.FRand(), Acc = 0.f;
		int32 Want = G - 1;
		for (int32 K = 0; K < G; ++K)
		{
			Acc += DistrictGroups[D * G + K];
			if (X < Acc)
			{
				Want = K;
				break;
			}
		}
		// (the last freed first: a scan from the end, then any slot of a group the district
		// has, then any)
		int32 Other = INDEX_NONE;
		for (int32 I = FreeSlots.Num() - 1, N = 0; I >= 0 && N < 800; --I, ++N)
		{
			const int32 S = FreeSlots[I];
			const int32 Gs = PersonGroup.IsValidIndex(S) ? PersonGroup[S] : -1;
			if (Gs == Want)
			{
				FreeSlots.RemoveAtSwap(I, EAllowShrinking::No);
				return S;
			}
			if (Other == INDEX_NONE && Gs >= 0 && Gs < G && DistrictGroups[D * G + Gs] > 0.f)
			{
				Other = I;
			}
		}
		if (Other != INDEX_NONE)
		{
			const int32 S = FreeSlots[Other];
			FreeSlots.RemoveAtSwap(Other, EAllowShrinking::No);
			return S;
		}
	}
	return FreeSlots.Pop(EAllowShrinking::No);
}

void ACityGenLife::DressSlot(const int32 Slot, const int32 D, FRandomStream& Rng)
{
	const int32 G = FMath::Max(1, OutfitGroupCount);
	const int32 K = FMath::Max(1, OutfitColors);
	const int32 Gs = FMath::Clamp(PersonGroup[Slot], 0, G - 1);
	PersonTint.SetNumZeroed(FMath::Max(PersonTint.Num(), 9 * People));
	for (int32 C = 0; C < 3; ++C)
	{
		const int32 Idx = Rng.RandRange(0, K - 1);
		const int32 B = 3 * ((D * G + Gs) * K + Idx);
		for (int32 Q = 0; Q < 3; ++Q)
		{
			PersonTint[9 * Slot + 3 * C + Q] = OutfitPalettes.IsValidIndex(B + Q) ? OutfitPalettes[B + Q] : 0.5f;
		}
	}
	PersonWear.SetNumZeroed(FMath::Max(PersonWear.Num(), People));
	const float W = DistrictWear.IsValidIndex(D) ? DistrictWear[D] : 0.3f;
	PersonWear[Slot] = FMath::Clamp(W + 0.3f * (Rng.FRand() - 0.5f), 0.f, 1.f);
}

void ACityGenLife::FreeOnDeadLanes()
{
	FMassEntityManager& EM = GetWorld()->GetSubsystem<UMassEntitySubsystem>()->GetMutableEntityManager();
	for (int32 Slot = 0; Slot < People && Slot < Entities.Num(); ++Slot)
	{
		FCgLifeWalker& W = EM.GetFragmentDataChecked<FCgLifeWalker>(Entities[Slot]);
		if (!W.Active || (InRegion.IsValidIndex(W.Lane) && InRegion[W.Lane]))
		{
			continue;
		}
		if (LaneHave.IsValidIndex(W.Lane))
		{
			--LaneHave[W.Lane];
		}
		// (LG4: its place slot let go)
		if (W.Slot != INDEX_NONE)
		{
			ReleasePoint(W.Slot, W.Point);
		}
		W.Slot = W.Point = INDEX_NONE;
		W.Active = 0;
		W.Door = INDEX_NONE;
		W.Visit = 0;
		W.State = CgWalk::Walk;
		W.Pos = FVector::ZeroVector;
		WalkState[Slot] = CgShow::Off;
		WalkPos[Slot] = FVector::ZeroVector;
		FreeRole(Slot);
		--ActiveNow;
		++Lost;
	}
}

void ACityGenLife::TakeFreed()
{
	for (const int32 Slot : Freed)
	{
		FreeRole(Slot);
		--ActiveNow;
	}
	Freed.Reset();
	DoorIn += Frame.Entered;
	JaywalkTotal += Frame.Jaywalked;
	WaitingNow = Frame.Waiting;
	VisitsTotal += Frame.Visits;
	TransitBoarded += Frame.Boarded;
	Frame.Boarded = 0;
	Frame.Entered = Frame.Exited = Frame.Jaywalked = 0;
	Frame.SlotsTaken = Frame.SlotsLeft = Frame.Visits = 0;
}

void ACityGenLife::UpdateLive(const float Dt, const bool bRefill)
{
	FVector View;
	if (!ViewPoint(View))
	{
		View = Ue(Center.X, Center.Y, 0.f);
	}
	LastLiveView = View;
	const double In = 100.0 * LiveM;
	const double Out = 100.0 * (LiveM + LiveMarginM);
	TArray<int32> Born, Died;
	bool bDied = false;
	WantLive = 0.f;
	WantGang = WantPolice = 0.f;
	LiveLanes = 0;
	const bool bPl = IsPlaces();
	const int32 Band = BandOf(Hour);
	for (int32 I = 0; I < WalkLaneCount; ++I)
	{
		const double D = FMath::Max(0.0, FVector::Dist(LaneMid[I], View) - LaneHalf[I]);
		const bool bWas = InRegion[I] != 0;
		const bool bLive = bWas ? D < Out : D < In;
		if (bLive != bWas)
		{
			InRegion[I] = bLive ? 1 : 0;
			if (bLive)
			{
				Born.Add(I);
			}
			else
			{
				bDied = true;
				Died.Add(I);
			}
		}
		if (bLive)
		{
			WantLive += Want(I);
			++LiveLanes;
			if (bPl)
			{
				// (LG4: the gang members and police walking it, its slots' users by their role)
				WantGang += RoleWant(I, CgRole::Gang);
				WantPolice += RoleWant(I, CgRole::Police);
				for (int32 K = LaneSlotStarts[I]; K < LaneSlotStarts[I + 1] && bPlaces; ++K)
				{
					const int32 Sl = LaneSlotList[K];
					if (SlotRoles[Sl] == CgRole::Gang)
					{
						WantGang += bGangs ? SlotWantOf(Sl) : 0.f;
					}
					else
					{
						WantLive += SlotWantOf(Sl) * CrowdScale;
					}
				}
			}
		}
	}
	(void)Band;
	// (the live people at most PoolFill of the pool: the density scaled down evenly; LG4: each
	// role within its own slots of the pool)
	const int32 NCrowd = bPl ? CrowdPoolN : People;
	LiveScale = WantLive > 0.f ? FMath::Min(1.f, PoolFill * (float)NCrowd / WantLive) : 1.f;
	GangScaleNow = WantGang > 0.f ? FMath::Min(1.f, PoolFill * (float)GangPoolN / WantGang) : 1.f;
	PoliceScaleNow = WantPolice > 0.f ? FMath::Min(1.f, PoolFill * (float)PolicePoolN / WantPolice) : 1.f;
	if (bRefill)
	{
		// (the hour or the scale changed: everyone out, every live walkway filled again)
		for (int32 I = 0; I < WalkLaneCount; ++I)
		{
			InRegion[I] = 0;
		}
		FreeOnDeadLanes();
		for (int32 I = 0; I < WalkLaneCount && bPl; ++I)
		{
			SlotsAlive(I, false);
		}
		Born.Reset();
		for (int32 I = 0; I < WalkLaneCount; ++I)
		{
			const double D = FMath::Max(0.0, FVector::Dist(LaneMid[I], View) - LaneHalf[I]);
			if (D < In)
			{
				InRegion[I] = 1;
				Born.Add(I);
			}
		}
	}
	else if (bDied)
	{
		FreeOnDeadLanes();
		for (const int32 Lane : Died)
		{
			if (bPl)
			{
				SlotsAlive(Lane, false);
			}
		}
	}
	for (const int32 Lane : Born)
	{
		const float N = Want(Lane) * LiveScale;
		int32 Count = (int32)N + (CrowdRng.FRand() < N - FMath::FloorToFloat(N) ? 1 : 0);
		while (Count > 0 && FreeSlots.Num())
		{
			const int32 Size = FMath::Min(GroupSize(CrowdRng), Count);
			const int32 Made = SpawnGroup(Lane, CrowdRng.FRand() * Lengths[Lane], CrowdRng.FRand() < 0.5f ? 1.f : -1.f, Size, INDEX_NONE, CrowdRng);
			if (Made == 0)
			{
				break;
			}
			Count -= Made;
		}
		if (bPl)
		{
			// (LG4: its gang members, police and slots' users)
			FillLaneRoles(Lane);
		}
	}
	if (bPl)
	{
		UpdateSlotWants();
	}
	// (the doors on live walkways, by their rates)
	if (Born.Num() || bDied || bRefill || DoorCum.Num() == 0)
	{
		DoorLive.Reset();
		DoorCum.Reset();
		float Tot = 0.f;
		for (int32 K = 0; K < DoorDists.Num(); ++K)
		{
			const int32 Ln = DoorLanesSorted[K];
			// (LG6: a served station's street accesses send no one out while transit runs: its
			// people come off the trains)
			const bool bByTrain = bTransit && IsTransit() && DoorTransitSorted.IsValidIndex(K) && DoorTransitSorted[K];
			if (InRegion[Ln] && DoorRatesSorted[K] > 0.f && !bByTrain)
			{
				Tot += DoorRatesSorted[K];
				DoorLive.Add(K);
				DoorCum.Add(Tot);
			}
		}
	}
}

void ACityGenLife::DoorSpawns(const float Dt)
{
	// (LG4: police pairs out of their stations' doors)
	PoliceFromStations(Dt);
	// (as many come out as go in over a trip, more while the live people are under their
	// number: the doors keep the streets at their density)
	const float Target = FMath::Min(WantLive, PoolFill * (float)(IsPlaces() ? CrowdPoolN : People));
	if (DoorCum.Num() == 0 || (float)ActiveNow >= 1.05f * Target)
	{
		DoorAcc = 0.f;
		return;
	}
	const float Rate = Target / FMath::Max(30.f, TripS) + FMath::Max(0.f, Target - (float)ActiveNow) / 30.f;
	DoorAcc += Rate * Dt;
	for (int32 Guard = 0; Guard < 64 && DoorAcc >= 1.f && FreeSlots.Num(); ++Guard)
	{
		const float X = CrowdRng.FRand() * DoorCum.Last();
		int32 Lo = 0, Hi = DoorCum.Num() - 1;
		while (Lo < Hi)
		{
			const int32 M = (Lo + Hi) / 2;
			if (DoorCum[M] < X) { Lo = M + 1; } else { Hi = M; }
		}
		const int32 Door = DoorLive[Lo];
		const int32 Size = FMath::Min(GroupSize(CrowdRng), (int32)DoorAcc);
		const int32 Made = SpawnGroup(DoorLanesSorted[Door], DoorDists[Door], CrowdRng.FRand() < 0.5f ? 1.f : -1.f, Size, Door, CrowdRng);
		if (Made == 0)
		{
			break;
		}
		DoorAcc -= (float)Made;
		++DoorOut;
	}
}

void ACityGenLife::SetHour(const int32 InHour)
{
	Hour = ((InHour % 24) + 24) % 24;
	if (bBuilt && IsPlaces())
	{
		// (LG4: the doors at the hour: open, their visits, their rates)
		ApplyHour();
	}
	if (bBuilt && IsCity())
	{
		UpdateLive(0.f, true);
	}
	if (bBuilt && IsTraffic() && bTraffic)
	{
		// (LG5: the traffic at the hour too)
		UpdateTraffic(0.f, true);
	}
}

void ACityGenLife::SetCrowdScale(const float InScale)
{
	CrowdScale = FMath::Max(0.f, InScale);
	if (bBuilt && IsCity())
	{
		UpdateLive(0.f, true);
	}
}

void ACityGenLife::ApplyLook(const int32 P, const bool bStill)
{
	// (the mid and far instances' custom data: the walk's loop, time offset and rate, its
	// passing pose held while the person stands; the outfit's tint: LookData)
	const int32 NC = MidMeshes.Num();
	if (NC == 0 || !PersonInst.IsValidIndex(P))
	{
		return;
	}
	const int32 C = PersonChar.IsValidIndex(P) ? FMath::Clamp(PersonChar[P], 0, NC - 1) : P % NC;
	float MidData[14], FarData[12];
	LookData(P, bStill, MidData, FarData);
	if (UInstancedStaticMeshComponent* Mid = MidComps.IsValidIndex(C) ? MidComps[C].Get() : nullptr)
	{
		Mid->SetCustomData(PersonInst[P], MakeArrayView(MidData, 14), false);
	}
	if (UInstancedStaticMeshComponent* Far = FarComps.IsValidIndex(C) ? FarComps[C].Get() : nullptr)
	{
		Far->SetCustomData(PersonInst[P], MakeArrayView(FarData, 12), false);
	}
	// (a near person takes its colors and wear when its slot is assigned: Assign)
}

FString ACityGenLife::CrowdStatus() const
{
	if (!IsCity())
	{
		return TEXT(",\"crowd\":null");
	}
	int32 Hidden = 0, Still = 0;
	for (const uint8 S : WalkState)
	{
		Hidden += S == CgShow::Hidden ? 1 : 0;
		Still += S == CgShow::Still ? 1 : 0;
	}
	return FString::Printf(TEXT(",\"crowd\":{\"hour\":%d,\"pool\":%d,\"live_m\":%.0f,\"live_lanes\":%d,\"want\":%.1f,\"scale\":%.3f,\"crowd_scale\":%.2f,\"active\":%d,\"free\":%d,\"waiting\":%d,\"still\":%d,\"in_elevators\":%d,\"spawned\":%d,\"door_out\":%d,\"door_in\":%d,\"lost\":%d,\"jaywalked\":%d,\"groups\":%d,\"doors\":%d,\"doors_live\":%d,\"signals\":%d}"),
		Hour, People, LiveM, LiveLanes, WantLive, LiveScale, CrowdScale, ActiveNow, FreeSlots.Num(), WaitingNow, Still, Hidden,
		Spawned, DoorOut, DoorIn, Lost, JaywalkTotal, GroupCounter, DoorDists.Num(), DoorLive.Num(), SignalWindows.Num() / 4)
		+ PlacesStatus();
}
