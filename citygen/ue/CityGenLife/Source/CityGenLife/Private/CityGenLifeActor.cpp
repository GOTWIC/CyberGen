// lifegen's runtime controller (LG0): see CityGenLifeActor.h.

#include "CityGenLifeActor.h"
#include "CityGenLifeProcessors.h"
#include "CityGenLifeTypes.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Algo/Sort.h"
#include "HAL/PlatformTime.h"
#include "MassEntityManager.h"
#include "MassEntitySubsystem.h"
#include "MassExecutor.h"
#include "MassProcessingContext.h"
#include "Materials/MaterialInterface.h"
#include "ZoneGraphData.h"
#include "ZoneGraphBVTree.h"
#include "ZoneGraphTypes.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(CityGenLifeActor)

namespace
{
	// ZoneGraph tags of the lanes: walkways and drive lanes (the default tag is bit 0)
	constexpr uint32 WalkTag = 1u << 1;
	constexpr uint32 DriveTag = 1u << 2;

	FVector Ue(const float X, const float Y, const float Z)
	{
		return FVector(X * 100.0, -Y * 100.0, Z * 100.0);
	}

	/** ZoneGraph's quantized BV-tree over the zones' boxes, built here: the engine's own
	 *  FZoneGraphBVTree::Build is not exported from the ZoneGraph module (5.8), so the same
	 *  tree (leaves in order of a median split on the longest axis, an internal node's index
	 *  minus the nodes under it, as its Query walks it) is made in a subclass and copied over. */
	struct FCgBVTree : public FZoneGraphBVTree
	{
		void Make(const TArray<FBox>& Boxes)
		{
			Nodes.Reset();
			FBox All(ForceInit);
			for (const FBox& B : Boxes)
			{
				All += B;
			}
			if (!All.IsValid)
			{
				return;
			}
			Origin = All.Min;
			const FVector Size = All.GetSize();
			const double Most = FMath::Max3(Size.X, Size.Y, Size.Z);
			QuantizationScale = Most > 0.0 ? float(MaxQuantizedCoord / Most) : 0.f;
			TArray<FZoneGraphBVNode> Items;
			Items.Reserve(Boxes.Num());
			for (int32 I = 0; I < Boxes.Num(); ++I)
			{
				FZoneGraphBVNode N = CalcNodeBounds(Boxes[I]);
				N.Index = I;
				Items.Add(N);
			}
			Nodes.Reserve(2 * Items.Num());
			Split(Items, 0, Items.Num());
		}

		void Split(TArray<FZoneGraphBVNode>& Items, const int32 Begin, const int32 End)
		{
			const int32 Here = Nodes.AddDefaulted();
			if (End - Begin == 1)
			{
				Nodes[Here] = Items[Begin];
				return;
			}
			FZoneGraphBVNode B = Items[Begin];
			for (int32 I = Begin + 1; I < End; ++I)
			{
				const FZoneGraphBVNode& N = Items[I];
				B.MinX = FMath::Min(B.MinX, N.MinX); B.MinY = FMath::Min(B.MinY, N.MinY); B.MinZ = FMath::Min(B.MinZ, N.MinZ);
				B.MaxX = FMath::Max(B.MaxX, N.MaxX); B.MaxY = FMath::Max(B.MaxY, N.MaxY); B.MaxZ = FMath::Max(B.MaxZ, N.MaxZ);
			}
			const int32 Dx = B.MaxX - B.MinX, Dy = B.MaxY - B.MinY, Dz = B.MaxZ - B.MinZ;
			const int32 Axis = (Dx >= Dy && Dx >= Dz) ? 0 : (Dy >= Dz ? 1 : 2);
			auto Mid = [Axis](const FZoneGraphBVNode& N)
			{
				return Axis == 0 ? int32(N.MinX) + N.MaxX : (Axis == 1 ? int32(N.MinY) + N.MaxY : int32(N.MinZ) + N.MaxZ);
			};
			Algo::Sort(MakeArrayView(Items.GetData() + Begin, End - Begin), [&Mid](const FZoneGraphBVNode& A, const FZoneGraphBVNode& C)
			{
				return Mid(A) < Mid(C) || (Mid(A) == Mid(C) && A.Index < C.Index);
			});
			const int32 Half = Begin + (End - Begin) / 2;
			Split(Items, Begin, Half);
			Split(Items, Half, End);
			B.Index = -(Nodes.Num() - Here);
			Nodes[Here] = B;
		}
	};

	uint32 Hash(const FString& S)
	{
		uint32 H = 2166136261u;
		for (const TCHAR C : S)
		{
			H = (H ^ (uint32)C) * 16777619u;
		}
		return H;
	}
}

ACityGenLife::ACityGenLife()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;
	PrimaryActorTick.TickGroup = TG_PrePhysics;
	RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent->SetMobility(EComponentMobility::Static);
}

ACityGenLife* ACityGenLife::Find(const UWorld* World)
{
	if (!World)
	{
		return nullptr;
	}
	TActorIterator<ACityGenLife> It(const_cast<UWorld*>(World));
	return It ? *It : nullptr;
}

void ACityGenLife::BeginPlay()
{
	Super::BeginPlay();
	const double T0 = FPlatformTime::Seconds();
	BuildLanes();
	if (!bBuilt)
	{
		UE_LOG(LogTemp, Warning, TEXT("CityGenLife: no lanes (the plan's spike has none); nothing moves"));
		return;
	}
	UMassEntitySubsystem* Sub = GetWorld()->GetSubsystem<UMassEntitySubsystem>();
	if (!Sub)
	{
		UE_LOG(LogTemp, Warning, TEXT("CityGenLife: no Mass entity subsystem in this world"));
		bBuilt = false;
		return;
	}
	FMassEntityManager& EM = Sub->GetMutableEntityManager();
	WalkProc = NewObject<UCityGenLifeWalkProcessor>(this);
	DriveProc = NewObject<UCityGenLifeDriveProcessor>(this);
	WalkProc->Frame = &Frame;
	DriveProc->Frame = &Frame;
	WalkProc->CallInitialize(this, EM.AsShared());
	DriveProc->CallInitialize(this, EM.AsShared());
	MakeComponents();
	SpawnAll();
	UE_LOG(LogTemp, Display, TEXT("CITYGEN_LIFE_READY {\"lanes\":%d,\"walk_lanes\":%d,\"drive_lanes\":%d,\"people\":%d,\"cars\":%d,\"ms\":%.1f}"),
		WalkLaneCount + DriveLaneCount, WalkLaneCount, DriveLaneCount, WalkPos.Num(), CarPos.Num(),
		(FPlatformTime::Seconds() - T0) * 1000.0);
}

void ACityGenLife::EndPlay(const EEndPlayReason::Type Reason)
{
	ClearEntities();
	if (Lanes)
	{
		Lanes->Destroy();
		Lanes = nullptr;
	}
	bBuilt = false;
	Super::EndPlay(Reason);
}

// --- the lanes ------------------------------------------------------------------------------

void ACityGenLife::BuildLanes()
{
	WalkLaneCount = FMath::Max(0, WalkStarts.Num() - 1);
	DriveLaneCount = FMath::Max(0, DriveStarts.Num() - 1);
	const int32 N = WalkLaneCount + DriveLaneCount;
	if (N == 0 || !GetWorld())
	{
		return;
	}
	FActorSpawnParameters P;
	P.Owner = this;
	P.ObjectFlags |= RF_Transient;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	Lanes = GetWorld()->SpawnActor<AZoneGraphData>(AZoneGraphData::StaticClass(), FTransform::Identity, P);
	if (!Lanes)
	{
		return;
	}
	Lengths.SetNumZeroed(N);
	Widths.SetNumZeroed(N);
	PointVmax.Reset();
	InRegion.SetNumZeroed(N);
	CarStarts.Reset();

	// (per lane its links, then flattened: a lane's links are contiguous in the storage)
	TArray<TArray<FZoneLaneLinkData>> Links;
	Links.SetNum(N);
	for (int32 I = 0; I < WalkLaneCount; ++I)
	{
		const int32 A = WalkLinkStarts.IsValidIndex(I) ? WalkLinkStarts[I] : 0;
		const int32 B = WalkLinkStarts.IsValidIndex(I + 1) ? WalkLinkStarts[I + 1] : A;
		for (int32 K = A; K < B && WalkLinks.IsValidIndex(K); ++K)
		{
			const int32 To = WalkLinks[K] >> 1;
			if (To >= 0 && To < WalkLaneCount && To != I)
			{
				Links[I].Add(FZoneLaneLinkData(To, (WalkLinks[K] & 1) ? EZoneLaneLinkType::Outgoing : EZoneLaneLinkType::Incoming, EZoneLaneLinkFlags::None));
			}
		}
	}
	for (int32 I = 0; I < DriveLaneCount; ++I)
	{
		const int32 A = DriveLinkStarts.IsValidIndex(I) ? DriveLinkStarts[I] : 0;
		const int32 B = DriveLinkStarts.IsValidIndex(I + 1) ? DriveLinkStarts[I + 1] : A;
		for (int32 K = A; K < B && DriveLinks.IsValidIndex(K); ++K)
		{
			const int32 To = DriveLinks[K];
			if (To >= 0 && To < DriveLaneCount && To != I)
			{
				Links[WalkLaneCount + I].Add(FZoneLaneLinkData(WalkLaneCount + To, EZoneLaneLinkType::Outgoing, EZoneLaneLinkFlags::None));
				Links[WalkLaneCount + To].Add(FZoneLaneLinkData(WalkLaneCount + I, EZoneLaneLinkType::Incoming, EZoneLaneLinkFlags::None));
			}
		}
	}

	const FVector2D C = Center;
	const float R2 = RadiusM * RadiusM;
	FScopeLock Lock(&Lanes->GetStorageLock());
	FZoneGraphStorage& S = Lanes->GetStorageMutable();
	S.Zones.Reset();
	S.Lanes.Reset();
	S.BoundaryPoints.Reset();
	S.LanePoints.Reset();
	S.LaneUpVectors.Reset();
	S.LaneTangentVectors.Reset();
	S.LanePointProgressions.Reset();
	S.LaneLinks.Reset();
	S.Bounds = FBox(ForceInit);
	TArray<FVector> Pts;
	TArray<float> PtV;
	for (int32 I = 0; I < N; ++I)
	{
		const bool bWalk = I < WalkLaneCount;
		const int32 J = bWalk ? I : I - WalkLaneCount;
		const TArray<float>& Flat = bWalk ? WalkPoints : DrivePoints;
		const TArray<int32>& St = bWalk ? WalkStarts : DriveStarts;
		const float W = 100.f * ((bWalk ? WalkWidths : DriveWidths).IsValidIndex(J) ? (bWalk ? WalkWidths : DriveWidths)[J] : 2.f);
		Pts.Reset();
		PtV.Reset();
		bool bIn = false;
		const bool bSpeeds = !bWalk && DriveVmax.Num() * 3 == DrivePoints.Num();
		for (int32 K = St[J]; K < St[J + 1]; ++K)
		{
			const float X = Flat[3 * K], Y = Flat[3 * K + 1], Z = Flat[3 * K + 2];
			bIn |= FVector2D::DistSquared(FVector2D(X, Y), C) <= R2;
			const FVector Q = Ue(X, Y, Z);
			const float V = bSpeeds ? 100.f * DriveVmax[K] : 0.f;
			if (Pts.Num() == 0 || FVector::DistSquared(Pts.Last(), Q) > 1.0)
			{
				Pts.Add(Q);
				PtV.Add(V);
			}
			else
			{
				PtV.Last() = FMath::Min(PtV.Last(), V);
			}
		}
		if (Pts.Num() == 0)
		{
			Pts.Add(FVector::ZeroVector);
		}
		if (Pts.Num() == 1)
		{
			Pts.Add(Pts[0] + FVector(1.0, 0.0, 0.0));
		}
		while (PtV.Num() < Pts.Num())
		{
			PtV.Add(PtV.Num() ? PtV.Last() : 0.f);
		}
		PointVmax.Append(PtV.GetData(), Pts.Num());
		FZoneLaneData L;
		L.Width = W;
		L.Tags = FZoneGraphTagMask(bWalk ? WalkTag : DriveTag);
		L.PointsBegin = S.LanePoints.Num();
		float Prog = 0.f;
		FBox Box(ForceInit);
		for (int32 K = 0; K < Pts.Num(); ++K)
		{
			if (K > 0)
			{
				Prog += FVector::Dist(Pts[K - 1], Pts[K]);
			}
			const FVector T = (Pts[FMath::Min(K + 1, Pts.Num() - 1)] - Pts[FMath::Max(K - 1, 0)]).GetSafeNormal();
			S.LanePoints.Add(Pts[K]);
			S.LaneTangentVectors.Add(T);
			S.LaneUpVectors.Add(FVector::UpVector);
			S.LanePointProgressions.Add(Prog);
			Box += Pts[K];
		}
		L.PointsEnd = S.LanePoints.Num();
		L.LinksBegin = S.LaneLinks.Num();
		S.LaneLinks.Append(Links[I]);
		L.LinksEnd = S.LaneLinks.Num();
		L.ZoneIndex = S.Zones.Num();
		S.Lanes.Add(L);
		FZoneData Zone;
		Zone.LanesBegin = I;
		Zone.LanesEnd = I + 1;
		Zone.BoundaryPointsBegin = Zone.BoundaryPointsEnd = S.BoundaryPoints.Num();
		Zone.Bounds = Box.ExpandBy(FVector(0.5f * W, 0.5f * W, 200.f));
		Zone.Tags = L.Tags;
		S.Zones.Add(Zone);
		S.Bounds += Zone.Bounds;
		Lengths[I] = FMath::Max(Prog, 1.f);
		Widths[I] = W;
		InRegion[I] = bIn ? 1 : 0;
		if (!bWalk && bIn && DriveStartable.IsValidIndex(J) && DriveStartable[J])
		{
			CarStarts.Add(I);
		}
	}
	{
		TArray<FBox> Boxes;
		Boxes.Reserve(S.Zones.Num());
		for (const FZoneData& Z : S.Zones)
		{
			Boxes.Add(Z.Bounds);
		}
		FCgBVTree Tree;
		Tree.Make(Boxes);
		S.ZoneBVTree = Tree;
	}
	Lanes->UpdateDrawing();

	Frame.Storage = &S;
	Frame.WalkLanes = WalkLaneCount;
	Frame.Lengths = &Lengths;
	Frame.Widths = &Widths;
	Frame.InRegion = &InRegion;
	Frame.CarStarts = &CarStarts;
	Frame.CarGap = CarGapM * 100.f;
	Frame.PointVmax = DriveVmax.Num() ? &PointVmax : nullptr;
	Frame.WalkPos = &WalkPos;
	Frame.WalkYaw = &WalkYaw;
	Frame.CarPos = &CarPos;
	Frame.CarYaw = &CarYaw;
	bBuilt = true;
}

// --- the stand-ins and the cars ---------------------------------------------------------------

void ACityGenLife::MakeComponents()
{
	auto Make = [this](const TCHAR* Name, UStaticMesh* Mesh, UMaterialInterface* Mat, int32 Floats, bool bShadow)
	{
		UInstancedStaticMeshComponent* C = NewObject<UInstancedStaticMeshComponent>(this, Name);
		C->SetMobility(EComponentMobility::Movable);
		C->SetupAttachment(RootComponent);
		C->SetStaticMesh(Mesh);
		if (Mat)
		{
			C->SetMaterial(0, Mat);
		}
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCanEverAffectNavigation(false);
		C->SetCastShadow(bShadow);
		// (out of Lumen's scene and the distance fields: moving every frame, the stand-ins'
		// basic shapes cost Lumen's scene update 9 ms a frame on the spike's first run, as
		// characters stay out of it in games)
		C->bAffectDistanceFieldLighting = bInLumen;
		C->SetAffectDynamicIndirectLighting(bInLumen);
		C->NumCustomDataFloats = Floats;
		C->RegisterComponent();
		return C;
	};
	if (HasPeople())
	{
		// (LG1: the library's people in place of the stand-ins)
		MakePeople();
	}
	else
	{
		if (BodyMesh)
		{
			Bodies = Make(TEXT("StandInBodies"), BodyMesh, StandInMaterial, 3, bShadows);
		}
		if (HeadMesh)
		{
			Heads = Make(TEXT("StandInHeads"), HeadMesh, StandInMaterial, 3, bShadows);
		}
	}
	CarParts.Reset();
	for (int32 P = 0; P < CarPartMeshes.Num(); ++P)
	{
		CarParts.Add(CarPartMeshes[P] ? Make(*FString::Printf(TEXT("CarPart%d"), P), CarPartMeshes[P], nullptr, PaintFloats, bShadows && (!CarPartShadows.IsValidIndex(P) || CarPartShadows[P] != 0)) : nullptr);
	}
}

void ACityGenLife::ClearEntities()
{
	if (Entities.Num() && GetWorld())
	{
		if (UMassEntitySubsystem* Sub = GetWorld()->GetSubsystem<UMassEntitySubsystem>())
		{
			Sub->GetMutableEntityManager().BatchDestroyEntities(Entities);
		}
	}
	Entities.Reset();
}

void ACityGenLife::SpawnAll()
{
	ClearEntities();
	UMassEntitySubsystem* Sub = GetWorld()->GetSubsystem<UMassEntitySubsystem>();
	FMassEntityManager& EM = Sub->GetMutableEntityManager();
	FRandomStream Rng((int32)Hash(City + DistrictId + PlanHash));

	// (people on the region's walkway lanes, each lane's share by its length, densest round
	// the region's middle and thinning out, 1 / (1 + (d / CrowdFalloffM)^2): the budget's
	// people within 300 m of a view where the benchmark walks)
	const FZoneGraphStorage& St = *Frame.Storage;
	const FVector Middle = Ue(Center.X, Center.Y, 0.f);
	auto Near = [&](const int32 I)
	{
		const FZoneLaneData& L = St.Lanes[I];
		const FVector P = 0.5 * (St.LanePoints[L.PointsBegin] + St.LanePoints[L.PointsEnd - 1]);
		const double D = FVector::Dist2D(P, Middle) / (100.0 * FMath::Max(1.f, CrowdFalloffM));
		return float(1.0 / (1.0 + D * D));
	};
	TArray<int32> WalkIn;
	TArray<float> Cum;
	float Tot = 0.f;
	for (int32 I = 0; I < WalkLaneCount; ++I)
	{
		if (InRegion[I])
		{
			Tot += Lengths[I] * Near(I);
			WalkIn.Add(I);
			Cum.Add(Tot);
		}
	}
	TArray<float> CarCum;
	float CarTot = 0.f;
	for (const int32 I : CarStarts)
	{
		CarTot += Lengths[I] * Near(I);
		CarCum.Add(CarTot);
	}
	auto PickCar = [&]()
	{
		const float Pick = Rng.FRand() * CarTot;
		int32 Lo = 0, Hi = CarCum.Num() - 1;
		while (Lo < Hi)
		{
			const int32 M = (Lo + Hi) / 2;
			if (CarCum[M] < Pick) { Lo = M + 1; } else { Hi = M; }
		}
		return CarStarts[Lo];
	};
	const int32 NP = WalkIn.Num() ? FMath::Max(0, People) : 0;
	WalkPos.SetNumZeroed(NP);
	WalkYaw.SetNumZeroed(NP);
	if (NP)
	{
		const FMassArchetypeHandle Arch = EM.CreateArchetype({FCgLifeWalker::StaticStruct()});
		TArray<FMassEntityHandle> Hs;
		EM.BatchCreateEntities(Arch, NP, Hs);
		for (int32 K = 0; K < Hs.Num(); ++K)
		{
			FCgLifeWalker& W = EM.GetFragmentDataChecked<FCgLifeWalker>(Hs[K]);
			const float Pick = Rng.FRand() * Tot;
			int32 Lo = 0, Hi = Cum.Num() - 1;
			while (Lo < Hi)
			{
				const int32 Mid = (Lo + Hi) / 2;
				if (Cum[Mid] < Pick) { Lo = Mid + 1; } else { Hi = Mid; }
			}
			W.Lane = WalkIn[Lo];
			W.Dist = Rng.FRand() * Lengths[W.Lane];
			W.Dir = Rng.FRand() < 0.5f ? 1.f : -1.f;
			W.Speed = 100.f * FMath::Lerp((float)WalkSpeed.X, (float)WalkSpeed.Y, Rng.FRand());
			if (PersonPace.IsValidIndex(K))
			{
				// (LG1: the person's own pace, as the plan drew it)
				W.Speed = 100.f * PersonPace[K];
			}
			// (most keep right, some left, across the walkway's width)
			W.Side = (Rng.FRand() < 0.75f ? 1.f : -1.f) * FMath::Lerp(0.15f, 0.8f, Rng.FRand());
			W.Instance = K;
			W.Seed = (uint32)Rng.GetUnsignedInt() | 1u;
		}
		Entities.Append(Hs);
	}

	// (the cars on the region's lanes, apart by their gap)
	// (more cars than the plan drew: its models and paints again in turn)
	const int32 NC = CarStarts.Num() && CarModels.Num() ? FMath::Max(0, Cars) : 0;
	CarOf.SetNumZeroed(NC);
	for (int32 K = 0; K < NC; ++K)
	{
		CarOf[K] = K % CarModels.Num();
	}
	CarPos.SetNumZeroed(NC);
	CarYaw.SetNumZeroed(NC);
	CarModelCount.Reset();
	CarInstance.SetNumZeroed(NC);
	int32 Models = 0;
	for (const int32 M : CarPartModels)
	{
		Models = FMath::Max(Models, M + 1);
	}
	CarModelCount.SetNumZeroed(Models);
	if (NC)
	{
		const FMassArchetypeHandle Arch = EM.CreateArchetype({FCgLifeCar::StaticStruct()});
		TArray<FMassEntityHandle> Hs;
		EM.BatchCreateEntities(Arch, NC, Hs);
		TMap<int32, TArray<float>> Taken;
		for (int32 K = 0; K < Hs.Num(); ++K)
		{
			FCgLifeCar& Car = EM.GetFragmentDataChecked<FCgLifeCar>(Hs[K]);
			Car.Seed = (uint32)Rng.GetUnsignedInt() | 1u;
			for (int32 Try = 0; Try < 12; ++Try)
			{
				Car.Lane = PickCar();
				Car.Dist = Rng.FRand() * Lengths[Car.Lane];
				bool bClear = true;
				for (const float D : Taken.FindOrAdd(Car.Lane))
				{
					bClear &= FMath::Abs(D - Car.Dist) > 2.f * Frame.CarGap;
				}
				if (bClear)
				{
					break;
				}
			}
			Taken.FindOrAdd(Car.Lane).Add(Car.Dist);
			Car.Cruise = 100.f * FMath::Lerp((float)DriveSpeed.X, (float)DriveSpeed.Y, Rng.FRand());
			// (cars_steam: its share of each lane's speed, by its draw)
			Car.Share = FMath::Lerp((float)DriveVary.X, (float)DriveVary.Y, Rng.FRand());
			Car.Speed = Car.Cruise * 0.5f;
			Car.Model = FMath::Clamp(CarModels[CarOf[K]], 0, FMath::Max(0, Models - 1));
			Car.Index = K;
			Car.Instance = CarModelCount.IsValidIndex(Car.Model) ? CarModelCount[Car.Model]++ : 0;
			CarInstance[K] = Car.Instance;
			const FZoneGraphStorage& S = *Frame.Storage;
			const FZoneLaneData& L = S.Lanes[Car.Lane];
			int32 Cands[24];
			int32 Nc = 0;
			for (int32 Q = L.LinksBegin; Q < L.LinksEnd && Nc < 24; ++Q)
			{
				if (S.LaneLinks[Q].Type == EZoneLaneLinkType::Outgoing)
				{
					Cands[Nc++] = S.LaneLinks[Q].DestLaneIndex;
				}
			}
			Car.Next = Nc ? Cands[Rng.RandHelper(Nc)] : INDEX_NONE;
		}
		Entities.Append(Hs);
	}

	// (the instances: one a person in each stand-in component, one a car of its model in each
	// of the model's parts; colors and paint once)
	if (HasPeople())
	{
		SpawnPeople(NP);
	}
	Scratch.Init(FTransform::Identity, NP);
	for (UInstancedStaticMeshComponent* Comp : {Bodies.Get(), Heads.Get()})
	{
		if (!Comp)
		{
			continue;
		}
		Comp->ClearInstances();
		Comp->AddInstances(Scratch, false, true, false);
		const int32 NColors = Palette.Num() / 3;
		for (int32 K = 0; K < NP && NColors > 0; ++K)
		{
			const int32 Ci = (int32)(Hash(FString::FromInt(K) + DistrictId) % (uint32)NColors);
			const float Shade = Comp == Heads ? 0.f : 1.f;
			float Rgb[3];
			for (int32 Q = 0; Q < 3; ++Q)
			{
				// (the head a skin tone from the person's hash, the body its style's color)
				const float Skin[3] = {0.45f, 0.28f, 0.18f};
				const float T = 0.35f + 0.65f * ((Hash(FString::FromInt(K) + TEXT("skin")) % 1000) / 1000.f);
				Rgb[Q] = Shade > 0.f ? Palette[3 * Ci + Q] : Skin[Q] * T;
			}
			Comp->SetCustomData(K, MakeArrayView(Rgb, 3), false);
		}
		Comp->MarkRenderStateDirty();
	}
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
		Scratch.Init(FTransform::Identity, Count);
		Comp->AddInstances(Scratch, false, true, false);
		for (int32 K = 0; K < NC; ++K)
		{
			if (CarModels[CarOf[K]] == M && CarPaints.Num() >= (CarOf[K] + 1) * PaintFloats)
			{
				Comp->SetCustomData(CarInstance[K], MakeArrayView(&CarPaints[CarOf[K] * PaintFloats], PaintFloats), false);
			}
		}
		Comp->MarkRenderStateDirty();
	}
}

void ACityGenLife::Respawn(int32 InPeople, int32 InCars)
{
	People = FMath::Max(0, InPeople);
	Cars = FMath::Max(0, InCars);
	if (bBuilt)
	{
		SpawnAll();
	}
}

void ACityGenLife::SetEnabled(bool bOn)
{
	bEnabled = bOn;
	for (UInstancedStaticMeshComponent* C : {Bodies.Get(), Heads.Get()})
	{
		if (C) { C->SetVisibility(bOn); }
	}
	for (UInstancedStaticMeshComponent* C : CarParts)
	{
		if (C) { C->SetVisibility(bOn); }
	}
	for (UInstancedStaticMeshComponent* C : MidComps)
	{
		if (C) { C->SetVisibility(bOn); }
	}
	for (UInstancedStaticMeshComponent* C : FarComps)
	{
		if (C) { C->SetVisibility(bOn); }
	}
	for (int32 S = 0; S < NearSlots.Num(); ++S)
	{
		if (!bOn)
		{
			Release(S);
		}
	}
}

void ACityGenLife::SetShadows(bool bOn)
{
	bShadows = bOn;
	for (UInstancedStaticMeshComponent* C : {Bodies.Get(), Heads.Get()})
	{
		if (C) { C->SetCastShadow(bOn); }
	}
	for (int32 P = 0; P < CarParts.Num(); ++P)
	{
		if (CarParts[P])
		{
			CarParts[P]->SetCastShadow(bOn && (!CarPartShadows.IsValidIndex(P) || CarPartShadows[P] != 0));
		}
	}
	for (UInstancedStaticMeshComponent* C : MidComps)
	{
		if (C) { C->SetCastShadow(bOn); }
	}
	for (USkeletalMeshComponent* C : NearComps)
	{
		if (C) { C->SetCastShadow(bOn); }
	}
}

void ACityGenLife::SetLumen(bool bOn)
{
	bInLumen = bOn;
	TArray<UInstancedStaticMeshComponent*> All = {Bodies.Get(), Heads.Get()};
	for (UInstancedStaticMeshComponent* C : CarParts)
	{
		All.Add(C);
	}
	for (UInstancedStaticMeshComponent* C : All)
	{
		if (C)
		{
			C->bAffectDistanceFieldLighting = bOn;
			C->SetAffectDynamicIndirectLighting(bOn);
			C->MarkRenderStateDirty();
		}
	}
}

// --- each frame -----------------------------------------------------------------------------

void ACityGenLife::FindGround()
{
	UWorld* World = GetWorld();
	UMassEntitySubsystem* Sub = World ? World->GetSubsystem<UMassEntitySubsystem>() : nullptr;
	if (!Sub || Entities.Num() == 0)
	{
		return;
	}
	FMassEntityManager& EM = Sub->GetMutableEntityManager();
	FCollisionQueryParams Q(SCENE_QUERY_STAT(CityGenLifeGround), false, this);
	const int32 N = FMath::Min(TracesPerFrame, Entities.Num());
	for (int32 K = 0; K < N; ++K)
	{
		TraceCursor = (TraceCursor + 1) % Entities.Num();
		const FMassEntityHandle H = Entities[TraceCursor];
		if (!EM.IsEntityValid(H))
		{
			continue;
		}
		float* ZOff = nullptr;
		FVector At;
		if (FCgLifeWalker* W = EM.GetFragmentDataPtr<FCgLifeWalker>(H))
		{
			ZOff = &W->ZOff;
			At = W->Pos;
		}
		else if (FCgLifeCar* C = EM.GetFragmentDataPtr<FCgLifeCar>(H))
		{
			ZOff = &C->ZOff;
			At = C->Pos;
		}
		if (!ZOff || At.IsZero())
		{
			continue;
		}
		const float LaneZ = At.Z - *ZOff;
		FHitResult Hit;
		if (World->LineTraceSingleByChannel(Hit, FVector(At.X, At.Y, LaneZ + 250.f), FVector(At.X, At.Y, LaneZ - 300.f), ECC_Visibility, Q))
		{
			*ZOff = FMath::Clamp((float)(Hit.ImpactPoint.Z - LaneZ), -150.f, 250.f);
		}
	}
}

void ACityGenLife::UpdateInstances()
{
	const int32 NP = WalkPos.Num();
	if (HasPeople())
	{
		UpdatePeople();
	}
	if (Bodies && NP)
	{
		Scratch.SetNum(NP);
		for (int32 K = 0; K < NP; ++K)
		{
			Scratch[K] = FTransform(FRotator(0.f, WalkYaw[K], 0.f), WalkPos[K] + FVector(0.f, 0.f, 78.f), FVector(0.30f, 0.44f, 1.5f));
		}
		Bodies->BatchUpdateInstancesTransforms(0, Scratch, false, bRebuildRenderState, false);
	}
	if (Heads && NP)
	{
		Scratch.SetNum(NP);
		for (int32 K = 0; K < NP; ++K)
		{
			Scratch[K] = FTransform(FRotator(0.f, WalkYaw[K], 0.f), WalkPos[K] + FVector(0.f, 0.f, 166.f), FVector(0.22f, 0.20f, 0.25f));
		}
		Heads->BatchUpdateInstancesTransforms(0, Scratch, false, bRebuildRenderState, false);
	}
	const int32 NC = CarPos.Num();
	for (int32 P = 0; P < CarParts.Num(); ++P)
	{
		UInstancedStaticMeshComponent* Comp = CarParts[P];
		if (!Comp || NC == 0)
		{
			continue;
		}
		const int32 M = CarPartModels.IsValidIndex(P) ? CarPartModels[P] : 0;
		const FVector Pivot = CarPartPivots.Num() >= 3 * (P + 1) ? Ue(CarPartPivots[3 * P], CarPartPivots[3 * P + 1], CarPartPivots[3 * P + 2]) : FVector::ZeroVector;
		Scratch.SetNum(CarModelCount.IsValidIndex(M) ? CarModelCount[M] : 0);
		for (int32 K = 0; K < NC; ++K)
		{
			if (CarModels[CarOf[K]] != M || !Scratch.IsValidIndex(CarInstance[K]))
			{
				continue;
			}
			const FTransform Car(FRotator(0.f, CarYaw[K], 0.f), CarPos[K]);
			Scratch[CarInstance[K]] = FTransform(Pivot) * Car;
		}
		Comp->BatchUpdateInstancesTransforms(0, Scratch, false, bRebuildRenderState, false);
	}
}

void ACityGenLife::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!bBuilt || !bEnabled)
	{
		return;
	}
	const double T0 = FPlatformTime::Seconds();
	UMassEntitySubsystem* Sub = GetWorld()->GetSubsystem<UMassEntitySubsystem>();
	if (!Sub)
	{
		return;
	}
	FMassEntityManager& EM = Sub->GetMutableEntityManager();
	FindGround();
	{
		UE::Mass::FProcessingContext Ctx(EM, DeltaSeconds);
		UE::Mass::Executor::Run(*WalkProc, Ctx);
	}
	{
		UE::Mass::FProcessingContext Ctx(EM, DeltaSeconds);
		UE::Mass::Executor::Run(*DriveProc, Ctx);
	}
	UpdateInstances();
	const double Ms = (FPlatformTime::Seconds() - T0) * 1000.0;
	TickMs = Ticks ? 0.98 * TickMs + 0.02 * Ms : Ms;
	TickMsMax = FMath::Max(TickMsMax * 0.999, Ms);
	++Ticks;
	// (the state in the log now and then: a session's record of what lifegen did)
	if (Ticks == 300 || Ticks % 6000 == 0)
	{
		UE_LOG(LogTemp, Display, TEXT("CITYGEN_LIFE_STATUS %s"), *GetStatus());
	}
}

FString ACityGenLife::GetStatus() const
{
	// (where the first person and car are, citygen m, how many people are placed, and how
	// many instances are drawn)
	const FVector P0 = WalkPos.Num() ? WalkPos[0] / 100.0 : FVector::ZeroVector;
	const FVector C0 = CarPos.Num() ? CarPos[0] / 100.0 : FVector::ZeroVector;
	int32 Placed = 0;
	for (const FVector& P : WalkPos)
	{
		Placed += P.IsZero() ? 0 : 1;
	}
	// (LG1: the people library's tiers: how many people are near, mid and far now, the slots,
	// the game thread's time drawing them)
	int32 Slots = 0;
	for (const FNearSlot& S : NearSlots)
	{
		Slots += S.Person != INDEX_NONE ? 1 : 0;
	}
	const FString Lib = HasPeople()
		? FString::Printf(TEXT(",\"library\":{\"characters\":%d,\"near\":%d,\"mid\":%d,\"far\":%d,\"slots\":%d,\"slots_made\":%d,\"near_m\":%.0f,\"near_max\":%d,\"mid_m\":%.0f,\"far_m\":%.0f,\"people_ms\":%.3f}"),
			MidMeshes.Num(), NearNow, MidNow, FarNow, Slots, NearSlots.Num(), NearM, NearMax, MidM, FarM, PeopleMs)
		: FString(TEXT(",\"library\":null"));
	return FString::Printf(TEXT("{\"enabled\":%s,\"built\":%s,\"district\":\"%s\",\"walk_lanes\":%d,\"drive_lanes\":%d,\"car_starts\":%d,\"people\":%d,\"cars\":%d,\"entities\":%d,\"placed\":%d,\"bodies\":%d,\"car_parts\":%d,\"person0\":[%.1f,%.1f,%.1f],\"car0\":[%.1f,%.1f,%.1f],\"tick_ms\":%.3f,\"tick_ms_max\":%.3f,\"ticks\":%lld%s}"),
		bEnabled ? TEXT("true") : TEXT("false"), bBuilt ? TEXT("true") : TEXT("false"), *DistrictId,
		WalkLaneCount, DriveLaneCount, CarStarts.Num(), WalkPos.Num(), CarPos.Num(), Entities.Num(), Placed,
		Bodies ? Bodies->GetInstanceCount() : -1, CarParts.Num(), P0.X, -P0.Y, P0.Z, C0.X, -C0.Y, C0.Z,
		TickMs, TickMsMax, (long long)Ticks, *Lib);
}
