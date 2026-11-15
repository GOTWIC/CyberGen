// lifegen's life at places (LG4): see CityGenLifeActor.h ("LG4: life at places"),
// CityGenLifePlaces.h and docs/unreal_export.md ("From LG4: life at places").
//
// The slots of a walkway are live while it is (LG3's live region round the view): each of their
// use points a Smart Object of the world's subsystem then, made and destroyed with its walkway.
// Every LiveStep s each live slot's wanted users are worked out (the plan's users at the hour,
// times the scale that keeps the pool's people within it); a walkway coming alive gets its
// slots' users at once (standing, sitting, talking there, part way through their stay), and
// people walking past a slot that wants users go to a free point (the walk processor claims it
// through the subsystem: ClaimPoint). Gang members and police are the pool's slots the plan keeps
// for them: a walkway coming alive in a gang's turf gets its gang members, walking in groups in
// their faction's colors, and its spots their loiterers; a patrol walkway its police in pairs;
// a precinct station's live doors send pairs out while the police round the view are under their
// number. Nothing here makes or destroys a Mass entity.

#include "CityGenLifePlaces.h"
#include "CityGenLifeActor.h"
#include "CityGenLifeTypes.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "MassEntityManager.h"
#include "MassEntitySubsystem.h"
#include "SmartObjectDefinition.h"
#include "SmartObjectSubsystem.h"
#include "UObject/UnrealType.h"
#include "ZoneGraphData.h"
#include "ZoneGraphQuery.h"
#include "ZoneGraphTypes.h"

namespace
{
	FVector UeP(const float X, const float Y, const float Z)
	{
		return FVector(X * 100.0, -Y * 100.0, Z * 100.0);
	}

	int32 BandOfH(const int32 Hour)
	{
		const int32 H = ((Hour % 24) + 24) % 24;
		return H < 6 ? 0 : (H < 10 ? 1 : (H < 16 ? 2 : (H < 20 ? 3 : 4)));
	}

	/** A count drawn from a mean: its whole part, one more by its fraction. */
	int32 Draw(const float N, FRandomStream& Rng)
	{
		return (int32)N + (Rng.FRand() < N - FMath::FloorToFloat(N) ? 1 : 0);
	}
}

// --- building ---------------------------------------------------------------------------------

void ACityGenLife::BuildPlaces()
{
	const FZoneGraphStorage& S = Lanes->GetStorage();
	const int32 NS = SlotKinds.Num();
	const int32 NL = WalkLaneCount;
	SlotDistCm.SetNumZeroed(NS);
	SlotLiveNow.Init(0, NS);
	SlotWantNow.SetNumZeroed(NS);
	SlotUsersNow.Init(0, NS);
	SlotAnimG.Init(CgAnim::Idle, NS);
	SlotDoorSorted.Init(INDEX_NONE, NS);
	SlotPointStartG.Init(0, NS + 1);
	PointPosG.Reset();
	PointYawG.Reset();
	for (int32 K = 0; K < NS; ++K)
	{
		const int32 Ln = SlotLanes.IsValidIndex(K) ? SlotLanes[K] : INDEX_NONE;
		const bool bLane = Ln >= 0 && Ln < NL;
		SlotDistCm[K] = bLane ? FMath::Clamp(100.f * SlotDists[K], 0.f, Lengths[Ln]) : 0.f;
		// (the slot's surface: its walkway's at its distance; the plan's points are over the
		// ground as the model has it, the walkway's z is the city's)
		float Z = 0.f;
		if (bLane)
		{
			FZoneGraphLaneLocation Loc;
			UE::ZoneGraph::Query::CalculateLocationAlongLane(S, Ln, SlotDistCm[K], Loc);
			Z = (float)Loc.Position.Z;
		}
		const int32 A = SlotPointStarts[K];
		const int32 B = SlotPointStarts[K + 1];
		for (int32 P = A; P < B && SlotPoints.IsValidIndex(4 * P + 3); ++P)
		{
			FVector At = UeP(SlotPoints[4 * P], SlotPoints[4 * P + 1], 0.f);
			At.Z = Z;
			PointPosG.Add(At);
			// (citygen's yaw is counterclockwise from east, y north; Unreal's Y is south)
			PointYawG.Add(FRotator::NormalizeAxis(-SlotPoints[4 * P + 3]));
		}
		SlotPointStartG[K + 1] = PointPosG.Num();
		const uint8 Code = SlotAnims.IsValidIndex(K) ? SlotAnims[K] : 0;
		SlotAnimG[K] = Code == 1 ? CgAnim::Sit : (Code == 2 ? CgAnim::Talk : CgAnim::Idle);
		const int32 Door = SlotDoors.IsValidIndex(K) ? SlotDoors[K] : INDEX_NONE;
		SlotDoorSorted[K] = DoorSortedOf.IsValidIndex(Door) ? DoorSortedOf[Door] : INDEX_NONE;
		if (!bLane)
		{
			SlotLanes[K] = INDEX_NONE;
		}
	}
	PointUser.Init(INDEX_NONE, PointPosG.Num());
	PointSO.SetNum(PointPosG.Num());
	// (each walkway's slots by their distance along it)
	TArray<int32> Order;
	for (int32 K = 0; K < NS; ++K)
	{
		if (SlotLanes[K] != INDEX_NONE)
		{
			Order.Add(K);
		}
	}
	Order.Sort([this](const int32 A, const int32 B)
	{
		return SlotLanes[A] < SlotLanes[B] || (SlotLanes[A] == SlotLanes[B] && SlotDistCm[A] < SlotDistCm[B]);
	});
	LaneSlotStarts.Init(0, NL + 1);
	LaneSlotList.Reset();
	for (const int32 K : Order)
	{
		LaneSlotList.Add(K);
		++LaneSlotStarts[SlotLanes[K] + 1];
	}
	for (int32 I = 0; I < NL; ++I)
	{
		LaneSlotStarts[I + 1] += LaneSlotStarts[I];
	}
	WalkAnimG.Init(CgAnim::Walk, FMath::Max(0, People));

	Frame.bPlaces = true;
	Frame.LaneSlotStarts = &LaneSlotStarts;
	Frame.LaneSlots = &LaneSlotList;
	Frame.SlotDist = &SlotDistCm;
	Frame.SlotLive = &SlotLiveNow;
	Frame.SlotRole = &SlotRoles;
	Frame.SlotAnim = &SlotAnimG;
	Frame.SlotTurf = &SlotTurfs;
	Frame.SlotDoor = &SlotDoorSorted;
	Frame.SlotWant = &SlotWantNow;
	Frame.SlotUsers = &SlotUsersNow;
	Frame.SlotDwell = &SlotDwell;
	Frame.SlotPointStart = &SlotPointStartG;
	Frame.PointPos = &PointPosG;
	Frame.PointYaw = &PointYawG;
	Frame.LaneTurf = &WalkTurf;
	Frame.LanePatrol = &WalkPatrol;
	Frame.DoorOpenNow = &DoorOpenNow;
	Frame.DoorVisitNow = &DoorVisitNow;
	Frame.DoorDwell = &DoorDwellSorted;
	Frame.DoorPolice = &DoorPoliceSorted;
	Frame.WalkAnim = &WalkAnimG;
	Frame.Claim = [this](const int32 Slot, const int32 Person) { return ClaimPoint(Slot, Person); };
	Frame.Occupy = [this](const int32 Slot, const int32 Point) { OccupyPoint(Slot, Point); };
	Frame.Release = [this](const int32 Slot, const int32 Point) { ReleasePoint(Slot, Point); };
	MakeDefinitions();
	ApplyHour();
}

void ACityGenLife::MakeDefinitions()
{
	// (a Smart Object definition per slot kind: one slot at its object's own transform, a
	// UCgPlaceBehaviorDefinition by default; its slots and behaviors set through reflection, the
	// engine keeps them to the editor otherwise)
	Definitions.Reset();
	FArrayProperty* SlotsProp = FindFProperty<FArrayProperty>(USmartObjectDefinition::StaticClass(), TEXT("Slots"));
	FArrayProperty* BehProp = FindFProperty<FArrayProperty>(USmartObjectDefinition::StaticClass(), TEXT("DefaultBehaviorDefinitions"));
	if (!SlotsProp || !BehProp)
	{
		UE_LOG(LogTemp, Warning, TEXT("CityGenLife: the Smart Object definition has no Slots or DefaultBehaviorDefinitions property; the slots are lifegen's alone"));
		return;
	}
	for (int32 K = 0; K < SlotKindNames.Num(); ++K)
	{
		const FString& Kind = SlotKindNames[K];
		USmartObjectDefinition* D = NewObject<USmartObjectDefinition>(this, *FString::Printf(TEXT("SO_CgPlace_%s"), *Kind));
		FScriptArrayHelper Slots(SlotsProp, SlotsProp->ContainerPtrToValuePtr<void>(D));
		Slots.AddValues(1);
		UCgPlaceBehaviorDefinition* B = NewObject<UCgPlaceBehaviorDefinition>(D);
		B->Kind = FName(*Kind);
		B->Behavior = FName(SlotKindBehaviors.IsValidIndex(K) ? *SlotKindBehaviors[K] : TEXT("use"));
		B->Clip = Kind == TEXT("bench") ? FName(TEXT("sit")) : FName(TEXT("idle"));
		TArray<TObjectPtr<USmartObjectBehaviorDefinition>>* Beh = BehProp->ContainerPtrToValuePtr<TArray<TObjectPtr<USmartObjectBehaviorDefinition>>>(D);
		Beh->Add(B);
		TArray<TPair<EMessageSeverity::Type, FText>> Errors;
		const bool bOk = D->Validate(&Errors);
		if (!bOk)
		{
			UE_LOG(LogTemp, Warning, TEXT("CityGenLife: the Smart Object definition of %s is not valid (%d issues: %s)"), *Kind, Errors.Num(),
				Errors.Num() ? *Errors[0].Value.ToString() : TEXT(""));
		}
		Definitions.Add(D);
	}
}

void ACityGenLife::ApplyHour()
{
	// (the doors at the hour: open, a passer-by's visit chance, their rates)
	const int32 H = ((Hour % 24) + 24) % 24;
	const int32 B = BandOfH(Hour);
	const int32 ND = DoorDists.Num();
	DoorOpenNow.Init(1, ND);
	DoorVisitNow.Init(0.f, ND);
	for (int32 K = 0; K < ND; ++K)
	{
		if (DoorOpenSorted.IsValidIndex(K))
		{
			DoorOpenNow[K] = (DoorOpenSorted[K] >> H) & 1 ? 1 : 0;
		}
		if (bPlaces && DoorVisitSorted.IsValidIndex(5 * K + B))
		{
			DoorVisitNow[K] = DoorVisitSorted[5 * K + B];
		}
		if (DoorRatesHSorted.IsValidIndex(24 * K + H) && DoorRatesSorted.IsValidIndex(K))
		{
			DoorRatesSorted[K] = DoorRatesHSorted[24 * K + H];
		}
	}
	DoorCum.Reset();
}

// --- the Smart Objects: live points, claims ---------------------------------------------------

void ACityGenLife::SlotsAlive(const int32 Lane, const bool bAlive)
{
	if (!LaneSlotStarts.IsValidIndex(Lane + 1))
	{
		return;
	}
	USmartObjectSubsystem* Sub = USmartObjectSubsystem::GetCurrent(GetWorld());
	for (int32 K = LaneSlotStarts[Lane]; K < LaneSlotStarts[Lane + 1]; ++K)
	{
		const int32 Sl = LaneSlotList[K];
		const uint8 PRole = SlotRoles.IsValidIndex(Sl) ? SlotRoles[Sl] : CgRole::Crowd;
		const bool bOn = bAlive && bPlaces && (PRole != CgRole::Gang || bGangs);
		if ((SlotLiveNow[Sl] != 0) == bOn)
		{
			continue;
		}
		SlotLiveNow[Sl] = bOn ? 1 : 0;
		SlotsLiveNow += bOn ? 1 : -1;
		const uint8 Kind = SlotKinds[Sl];
		const USmartObjectDefinition* Def = Definitions.IsValidIndex(Kind) ? Cast<USmartObjectDefinition>(Definitions[Kind]) : nullptr;
		for (int32 P = SlotPointStartG[Sl]; P < SlotPointStartG[Sl + 1]; ++P)
		{
			FCgPointSO& So = PointSO[P];
			if (bOn && Sub && Def)
			{
				So.Object = Sub->CreateSmartObject(*Def, FTransform(FRotator(0.f, PointYawG[P], 0.f), PointPosG[P]), FConstStructView());
				TArray<FSmartObjectSlotHandle> Handles;
				if (So.Object.IsValid())
				{
					Sub->GetAllSlots(So.Object, Handles);
					++PointsSO;
				}
				So.Slot = Handles.Num() ? Handles[0] : FSmartObjectSlotHandle();
			}
			else if (!bOn)
			{
				if (Sub && So.Claim.IsValid())
				{
					Sub->MarkSlotAsFree(So.Claim);
				}
				if (Sub && So.Object.IsValid())
				{
					Sub->DestroySmartObject(So.Object);
					--PointsSO;
				}
				So = FCgPointSO();
				if (PointUser[P] != INDEX_NONE)
				{
					PointUser[P] = INDEX_NONE;
					--SlotUsersNow[Sl];
				}
			}
		}
	}
}

int32 ACityGenLife::ClaimPoint(const int32 Slot, const int32 Person)
{
	if (!SlotLiveNow.IsValidIndex(Slot) || !SlotLiveNow[Slot])
	{
		return INDEX_NONE;
	}
	USmartObjectSubsystem* Sub = USmartObjectSubsystem::GetCurrent(GetWorld());
	const int32 A = SlotPointStartG[Slot];
	const int32 N = SlotPointStartG[Slot + 1] - A;
	// (the first free point, from a point by the person, so a queue fills from its front)
	const bool bQueue = SlotKinds.IsValidIndex(Slot) && SlotKindNames.IsValidIndex(SlotKinds[Slot]) &&
		(SlotKindNames[SlotKinds[Slot]] == TEXT("bar_queue") || SlotKindNames[SlotKinds[Slot]] == TEXT("taxi_stand") ||
		 SlotKindNames[SlotKinds[Slot]] == TEXT("kiosk") || SlotKindNames[SlotKinds[Slot]] == TEXT("vending"));
	const int32 Start = bQueue ? 0 : (int32)((uint32)Person * 2654435761u % (uint32)FMath::Max(1, N));
	for (int32 I = 0; I < N; ++I)
	{
		const int32 P = A + (Start + I) % N;
		if (PointUser[P] != INDEX_NONE)
		{
			continue;
		}
		FCgPointSO& So = PointSO[P];
		if (Sub && So.Slot.IsValid())
		{
			// (someone else, the game's own AI, may hold it)
			if (!Sub->CanBeClaimed(So.Slot))
			{
				++ClaimsRefused;
				continue;
			}
			So.Claim = Sub->MarkSlotAsClaimed(So.Slot, ESmartObjectClaimPriority::Normal);
			if (!So.Claim.IsValid())
			{
				++ClaimsRefused;
				continue;
			}
		}
		PointUser[P] = Person;
		++SlotUsersNow[Slot];
		return P;
	}
	return INDEX_NONE;
}

void ACityGenLife::OccupyPoint(const int32 Slot, const int32 Point)
{
	USmartObjectSubsystem* Sub = USmartObjectSubsystem::GetCurrent(GetWorld());
	if (Sub && PointSO.IsValidIndex(Point) && PointSO[Point].Claim.IsValid())
	{
		Sub->MarkSlotAsOccupied<UCgPlaceBehaviorDefinition>(PointSO[Point].Claim);
	}
	++SlotsTakenTotal;
}

void ACityGenLife::ReleasePoint(const int32 Slot, const int32 Point)
{
	if (!PointUser.IsValidIndex(Point) || PointUser[Point] == INDEX_NONE)
	{
		return;
	}
	USmartObjectSubsystem* Sub = USmartObjectSubsystem::GetCurrent(GetWorld());
	FCgPointSO& So = PointSO[Point];
	if (Sub && So.Claim.IsValid())
	{
		Sub->MarkSlotAsFree(So.Claim);
	}
	So.Claim = FSmartObjectClaimHandle();
	PointUser[Point] = INDEX_NONE;
	if (SlotUsersNow.IsValidIndex(Slot))
	{
		--SlotUsersNow[Slot];
	}
	++SlotsLeftTotal;
}

// --- the wanted: slots, gangs, police ----------------------------------------------------------

float ACityGenLife::RoleWant(const int32 Lane, const uint8 PRole) const
{
	const int32 B = BandOfH(Hour);
	const int32 D = LaneDistrictArr.IsValidIndex(Lane) ? LaneDistrictArr[Lane] : INDEX_NONE;
	const int32 H = ((Hour % 24) + 24) % 24;
	const float Shape = (D >= 0 && DistrictShape.IsValidIndex(24 * D + H)) ? DistrictShape[24 * D + H] : 1.f;
	if (PRole == CgRole::Gang)
	{
		return bGangs && WalkGang.IsValidIndex(5 * Lane + B) ? WalkGang[5 * Lane + B] * Shape : 0.f;
	}
	if (PRole == CgRole::Police)
	{
		return bPolice && WalkPolice.IsValidIndex(5 * Lane + B) ? WalkPolice[5 * Lane + B] * Shape : 0.f;
	}
	return 0.f;
}

float ACityGenLife::SlotWantOf(const int32 K) const
{
	// (a slot's users at the hour: the plan's by band, its district's day, the scale that keeps
	// its role's people within the pool; at most its points)
	if (!SlotLanes.IsValidIndex(K) || SlotLanes[K] == INDEX_NONE)
	{
		return 0.f;
	}
	const int32 B = BandOfH(Hour);
	const int32 H = ((Hour % 24) + 24) % 24;
	const int32 Ln = SlotLanes[K];
	const int32 D = LaneDistrictArr.IsValidIndex(Ln) ? LaneDistrictArr[Ln] : INDEX_NONE;
	const float Shape = (D >= 0 && DistrictShape.IsValidIndex(24 * D + H)) ? DistrictShape[24 * D + H] : 1.f;
	const float Use = SlotUse.IsValidIndex(5 * K + B) ? SlotUse[5 * K + B] : 0.f;
	const int32 Cap = SlotPointStartG[K + 1] - SlotPointStartG[K];
	return FMath::Min((float)Cap, Use * Shape);
}

void ACityGenLife::UpdateSlotWants()
{
	for (int32 K = 0; K < SlotKinds.Num(); ++K)
	{
		const float Scale = SlotRoles[K] == CgRole::Gang ? GangScaleNow : CrowdScale * LiveScale;
		SlotWantNow[K] = SlotLiveNow[K] ? SlotWantOf(K) * Scale : 0.f;
	}
}

// --- filling a walkway coming alive ------------------------------------------------------------

void ACityGenLife::FillLaneRoles(const int32 Lane)
{
	// (its gang members in groups, its police in pairs; its slots alive and their users)
	if (bGangs && WalkTurf.IsValidIndex(Lane) && WalkTurf[Lane] >= 0)
	{
		int32 Count = Draw(RoleWant(Lane, CgRole::Gang) * GangScaleNow, CrowdRng);
		while (Count > 0 && FreeGang.Num())
		{
			float X = CrowdRng.FRand();
			int32 Size = 1;
			float Tot = 0.f;
			for (const float V : GangGroups)
			{
				Tot += V;
			}
			X *= Tot > 0.f ? Tot : 1.f;
			for (int32 K = 0; K < GangGroups.Num(); ++K)
			{
				X -= GangGroups[K];
				if (X < 0.f)
				{
					Size = K + 1;
					break;
				}
			}
			const int32 Made = SpawnGroup(Lane, CrowdRng.FRand() * Lengths[Lane], CrowdRng.FRand() < 0.5f ? 1.f : -1.f,
				FMath::Min(Size, Count), INDEX_NONE, CrowdRng, CgRole::Gang, WalkTurf[Lane]);
			if (Made == 0)
			{
				break;
			}
			Count -= Made;
		}
	}
	if (bPolice && WalkPatrol.IsValidIndex(Lane) && WalkPatrol[Lane])
	{
		int32 Count = Draw(RoleWant(Lane, CgRole::Police) * PoliceScaleNow, CrowdRng);
		while (Count > 0 && FreePolice.Num())
		{
			const int32 Made = SpawnGroup(Lane, CrowdRng.FRand() * Lengths[Lane], CrowdRng.FRand() < 0.5f ? 1.f : -1.f,
				2, INDEX_NONE, CrowdRng, CgRole::Police, INDEX_NONE);
			if (Made == 0)
			{
				break;
			}
			Count -= Made;
		}
	}
	if (LaneSlotStarts.IsValidIndex(Lane + 1))
	{
		SlotsAlive(Lane, true);
		for (int32 K = LaneSlotStarts[Lane]; K < LaneSlotStarts[Lane + 1]; ++K)
		{
			const int32 Sl = LaneSlotList[K];
			const float Scale = SlotRoles[Sl] == CgRole::Gang ? GangScaleNow : CrowdScale * LiveScale;
			SlotWantNow[Sl] = SlotLiveNow[Sl] ? SlotWantOf(Sl) * Scale : 0.f;
			FillSlot(Sl);
		}
	}
}

void ACityGenLife::FillSlot(const int32 Sl)
{
	if (!SlotLiveNow[Sl])
	{
		return;
	}
	const int32 Lane = SlotLanes[Sl];
	const uint8 PRole = SlotRoles[Sl];
	int32 Count = Draw(SlotWantNow[Sl], CrowdRng) - SlotUsersNow[Sl];
	FMassEntityManager& EM = GetWorld()->GetSubsystem<UMassEntitySubsystem>()->GetMutableEntityManager();
	TArray<int32> Made;
	for (; Count > 0; --Count)
	{
		if ((PRole == CgRole::Gang && !FreeGang.Num()) || (PRole == CgRole::Crowd && !FreeSlots.Num()) || PRole == CgRole::Police)
		{
			return;
		}
		Made.Reset();
		if (!SpawnGroup(Lane, SlotDistCm[Sl], CrowdRng.FRand() < 0.5f ? 1.f : -1.f, 1, INDEX_NONE, CrowdRng, PRole,
			SlotTurfs.IsValidIndex(Sl) ? SlotTurfs[Sl] : INDEX_NONE, &Made) || !Made.Num())
		{
			return;
		}
		const int32 Person = Made[0];
		FCgLifeWalker& W = EM.GetFragmentDataChecked<FCgLifeWalker>(Entities[Person]);
		const int32 P = ClaimPoint(Sl, Person);
		if (P == INDEX_NONE)
		{
			return;          // (it walks on: the slot is full)
		}
		// (there already, part way through its stay)
		W.Slot = Sl;
		W.Point = P;
		W.State = CgWalk::AtSlot;
		W.Anim = SlotAnimG[Sl];
		W.Pos = PointPosG[P];
		W.Yaw = PointYawG[P];
		W.Faced = 1;
		W.Dwell = FMath::Lerp(SlotDwell[2 * Sl], FMath::Max(SlotDwell[2 * Sl], SlotDwell[2 * Sl + 1]), CrowdRng.FRand()) * CrowdRng.FRand();
		W.PassedSlot = Sl;
		// (its walkway's line where the slot is, to go back to; its ground there, traced once:
		// the walkway's own surface, as a walker's)
		W.Dist = SlotDistCm[Sl];
		{
			FZoneGraphLaneLocation Loc;
			UE::ZoneGraph::Query::CalculateLocationAlongLane(Lanes->GetStorage(), Lane, W.Dist, Loc);
			FHitResult Hit;
			FCollisionQueryParams Q(SCENE_QUERY_STAT(CityGenLifeSlotGround), false, this);
			if (GetWorld()->LineTraceSingleByChannel(Hit, Loc.Position + FVector(0.f, 0.f, 250.f), Loc.Position - FVector(0.f, 0.f, 300.f), ECC_Visibility, Q))
			{
				W.ZOff = FMath::Clamp((float)(Hit.ImpactPoint.Z - Loc.Position.Z), -150.f, 250.f);
			}
			W.Pos = PointPosG[P] + FVector(0.f, 0.f, W.ZOff);
		}
		OccupyPoint(Sl, P);
		WalkPos[Person] = W.Pos;
		WalkYaw[Person] = W.Yaw;
		WalkState[Person] = CgShow::Still;
		WalkAnimG[Person] = W.Anim;
	}
}

void ACityGenLife::PoliceFromStations(const float Dt)
{
	// (a precinct station's live doors send pairs out while the police round the view are under
	// their number)
	if (!bPolice || !IsPlaces() || DoorLive.Num() == 0)
	{
		return;
	}
	const float Target = WantPolice * PoliceScaleNow;
	if ((float)PoliceActive >= Target || FreePolice.Num() < 2)
	{
		PoliceAcc = 0.f;
		return;
	}
	PoliceAcc += (Target - (float)PoliceActive) / 40.f * Dt;
	if (PoliceAcc < 2.f)
	{
		return;
	}
	TArray<int32> Live;
	for (const int32 K : DoorLive)
	{
		if (DoorPoliceSorted.IsValidIndex(K) && DoorPoliceSorted[K])
		{
			Live.Add(K);
		}
	}
	if (!Live.Num())
	{
		PoliceAcc = 0.f;
		return;
	}
	const int32 Door = Live[CrowdRng.RandRange(0, Live.Num() - 1)];
	if (SpawnGroup(DoorLanesSorted[Door], DoorDists[Door], CrowdRng.FRand() < 0.5f ? 1.f : -1.f, 2, Door, CrowdRng, CgRole::Police, INDEX_NONE))
	{
		++PoliceOut;
	}
	PoliceAcc = 0.f;
}

void ACityGenLife::DressFaction(const int32 Slot, const int32 Faction, FRandomStream& Rng)
{
	// (a gang member's dye: its faction's own color or a shade of it on the first channel, a dark
	// neutral or the color on the others)
	const int32 K = FMath::Max(1, FactionColors);
	PersonTint.SetNumZeroed(FMath::Max(PersonTint.Num(), 9 * People));
	for (int32 C = 0; C < 3; ++C)
	{
		const int32 Idx = C == 0 ? Rng.RandRange(0, FMath::Min(3, K - 1)) : Rng.RandRange(0, K - 1);
		const int32 B = 3 * (Faction * K + Idx);
		for (int32 Q = 0; Q < 3; ++Q)
		{
			PersonTint[9 * Slot + 3 * C + Q] = FactionPalettes.IsValidIndex(B + Q) ? FactionPalettes[B + Q] : 0.1f;
		}
	}
	PersonWear.SetNumZeroed(FMath::Max(PersonWear.Num(), People));
	PersonWear[Slot] = FMath::Clamp(0.45f + 0.4f * Rng.FRand(), 0.f, 1.f);
}

// --- the switches ------------------------------------------------------------------------------

void ACityGenLife::SetPlaces(const bool bOn)
{
	bPlaces = bOn;
	if (bBuilt && IsPlaces())
	{
		ApplyHour();
		UpdateLive(0.f, true);
	}
}

void ACityGenLife::SetGangs(const bool bOn)
{
	bGangs = bOn;
	if (bBuilt && IsPlaces())
	{
		UpdateLive(0.f, true);
	}
}

void ACityGenLife::SetPolice(const bool bOn)
{
	bPolice = bOn;
	if (bBuilt && IsPlaces())
	{
		UpdateLive(0.f, true);
		if (IsTraffic() && bTraffic)
		{
			UpdateTraffic(0.f, true);
		}
	}
}

// --- the check's shots -------------------------------------------------------------------------

bool ACityGenLife::ShowPlace(const FString& What)
{
	if (!bBuilt || !IsPlaces())
	{
		return false;
	}
	FVector View;
	if (!ViewPoint(View))
	{
		View = LastLiveView;
	}
	FMassEntityManager& EM = GetWorld()->GetSubsystem<UMassEntitySubsystem>()->GetMutableEntityManager();
	if (What == TEXT("patrol"))
	{
		int32 Best = INDEX_NONE;
		double BestD = 1.0e18;
		for (int32 Slot = 0; Slot < CarEnts.Num(); ++Slot)
		{
			const FCgLifeCar& C = EM.GetFragmentDataChecked<FCgLifeCar>(CarEnts[Slot]);
			if (!C.Active || !CarShow[Slot] || !CarIsPolice.IsValidIndex(Slot) || !CarIsPolice[Slot] || C.Speed < 300.f)
			{
				continue;
			}
			const double D = FVector::Dist(C.Pos, View);
			if (D < BestD)
			{
				BestD = D;
				Best = Slot;
			}
		}
		if (Best == INDEX_NONE)
		{
			UE_LOG(LogTemp, Display, TEXT("CITYGEN_LIFE_SHOW {\"what\":\"%s\",\"found\":false}"), *What);
			return false;
		}
		const FCgLifeCar& C = EM.GetFragmentDataChecked<FCgLifeCar>(CarEnts[Best]);
		const FVector Fwd(FMath::Cos(FMath::DegreesToRadians(C.Yaw)), FMath::Sin(FMath::DegreesToRadians(C.Yaw)), 0.0);
		const FVector P = C.Pos / 100.0;
		UE_LOG(LogTemp, Display, TEXT("CITYGEN_LIFE_SHOW {\"what\":\"%s\",\"found\":true,\"car\":%d,\"at\":[%.1f,%.1f,%.1f],\"speed\":%.2f}"),
			*What, Best, P.X, -P.Y, P.Z, C.Speed / 100.0);
		return FrameCar(C.Pos + Fwd * 1200.0, -Fwd, 1100.0, 350.0, 500.0);
	}
	int32 Best = INDEX_NONE;
	double Score = 1.0e18;
	for (int32 Pn = 0; Pn < People && Pn < Entities.Num(); ++Pn)
	{
		const FCgLifeWalker& W = EM.GetFragmentDataChecked<FCgLifeWalker>(Entities[Pn]);
		if (!W.Active || W.Pos.IsZero())
		{
			continue;
		}
		const FString Kind = (W.State == CgWalk::AtSlot && SlotKinds.IsValidIndex(W.Slot) && SlotKindNames.IsValidIndex(SlotKinds[W.Slot]))
			? SlotKindNames[SlotKinds[W.Slot]] : FString();
		bool bWant = false;
		int32 Bonus = 0;
		if (What == TEXT("sit"))
		{
			bWant = W.State == CgWalk::AtSlot && W.Anim == CgAnim::Sit;
		}
		else if (What == TEXT("queue"))
		{
			bWant = Kind == TEXT("bar_queue") || Kind == TEXT("bus_stop") || Kind == TEXT("taxi_stand");
		}
		else if (What == TEXT("stall"))
		{
			bWant = Kind == TEXT("stall") || Kind == TEXT("kiosk") || Kind == TEXT("vending");
		}
		else if (What == TEXT("smoke"))
		{
			bWant = Kind == TEXT("smoke");
		}
		else if (What == TEXT("gang"))
		{
			bWant = W.Role == CgRole::Gang && W.State == CgWalk::AtSlot;
		}
		else if (What == TEXT("gangwalk"))
		{
			bWant = W.Role == CgRole::Gang && W.State == CgWalk::Walk && W.Group != INDEX_NONE;
		}
		else if (What == TEXT("police"))
		{
			bWant = W.Role == CgRole::Police && W.State == CgWalk::Walk;
		}
		if (!bWant)
		{
			continue;
		}
		if (W.State == CgWalk::AtSlot && W.Slot != INDEX_NONE)
		{
			Bonus = SlotUsersNow[W.Slot];           // (a slot with more users first)
		}
		const double Sc = FVector::Dist(W.Pos, View) - 2000.0 * FMath::Min(Bonus, 4);
		if (Sc < Score)
		{
			Score = Sc;
			Best = Pn;
		}
	}
	if (Best == INDEX_NONE)
	{
		UE_LOG(LogTemp, Display, TEXT("CITYGEN_LIFE_SHOW {\"what\":\"%s\",\"found\":false}"), *What);
		return false;
	}
	const FCgLifeWalker& W = EM.GetFragmentDataChecked<FCgLifeWalker>(Entities[Best]);
	const FVector Face(FMath::Cos(FMath::DegreesToRadians(W.Yaw)), FMath::Sin(FMath::DegreesToRadians(W.Yaw)), 0.0);
	const FVector P = W.Pos / 100.0;
	UE_LOG(LogTemp, Display, TEXT("CITYGEN_LIFE_SHOW {\"what\":\"%s\",\"found\":true,\"person\":%d,\"at\":[%.1f,%.1f,%.1f],\"slot\":%d,\"users\":%d,\"role\":%d}"),
		*What, Best, P.X, -P.Y, P.Z, W.Slot, W.Slot != INDEX_NONE ? SlotUsersNow[W.Slot] : 0, (int32)W.Role);
	// (from in front of them, a little to the side and above)
	return FrameCar(W.Pos, -Face, 520.0, 150.0, 160.0);
}

// --- the status ----------------------------------------------------------------------------------

FString ACityGenLife::PlacesStatus() const
{
	if (!IsPlaces())
	{
		return TEXT(",\"places\":null");
	}
	TMap<FString, int32> ByKind;
	int32 Users = 0;
	for (int32 K = 0; K < SlotKinds.Num(); ++K)
	{
		if (SlotUsersNow[K] > 0 && SlotKindNames.IsValidIndex(SlotKinds[K]))
		{
			ByKind.FindOrAdd(SlotKindNames[SlotKinds[K]]) += SlotUsersNow[K];
			Users += SlotUsersNow[K];
		}
	}
	FString Kinds;
	for (const TPair<FString, int32>& KV : ByKind)
	{
		Kinds += FString::Printf(TEXT("%s\"%s\":%d"), Kinds.IsEmpty() ? TEXT("") : TEXT(","), *KV.Key, KV.Value);
	}
	int32 Open = 0;
	for (const uint8 O : DoorOpenNow)
	{
		Open += O;
	}
	return FString::Printf(TEXT(",\"places\":{\"on\":%s,\"gangs_on\":%s,\"police_on\":%s,\"slots\":%d,\"live\":%d,\"smart_objects\":%d,\"users\":%d,\"by_kind\":{%s},\"taken\":%d,\"left\":%d,\"refused\":%d,\"visits\":%d,\"doors_open\":%d,\"gang\":%d,\"gang_free\":%d,\"gang_want\":%.1f,\"gang_scale\":%.3f,\"police\":%d,\"police_free\":%d,\"police_want\":%.1f,\"police_scale\":%.3f,\"police_out\":%d,\"patrol_cars\":%d,\"patrol_cars_free\":%d,\"patrol_want\":%.1f,\"clips\":%s}"),
		bPlaces ? TEXT("true") : TEXT("false"), bGangs ? TEXT("true") : TEXT("false"), bPolice ? TEXT("true") : TEXT("false"),
		SlotKinds.Num(), SlotsLiveNow, PointsSO, Users, *Kinds, SlotsTakenTotal, SlotsLeftTotal, ClaimsRefused, VisitsTotal, Open,
		GangActive, FreeGang.Num(), WantGang, GangScaleNow, PoliceActive, FreePolice.Num(), WantPolice, PoliceScaleNow, PoliceOut,
		PoliceCarsActive, FreePoliceCars.Num(), WantPoliceCars, SitClips.Num() ? TEXT("true") : TEXT("false"));
}
