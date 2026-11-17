// lifegen's transit (LG6): see CityGenLifeActor.h ("LG6: transit") and docs/unreal_export.md
// ("From LG6: transit").
//
// Every line's trains run its timetable by the world's time: a train's place on its line's
// cycle is the cycle's sampled coordinate at (time + its phase) modulo the cycle, the phases
// spread evenly by the hour band's trains, so nothing is simulated and a train far off costs a
// lookup. Its cars follow the track (each car by the track's points at its two ends), on their
// way's own track (the right of it), crossing to the other before a turn. A train standing at a
// stop opens its doors after it halts and shuts them before it leaves; where the stop's
// platform walkway is live (LG3's live region round the view) people of the crowd leave it
// through its doors onto the platform and walk on (the walk processor's FromSlot, with no slot),
// and people on the platform walk into its doors and are gone (CgWalk::Board). The cars are
// instanced stand-ins of the exporter's per mode model table (one component per basic shape,
// a run of instances per train), their door leaves and lit doorways drawn near the view only.

#include "CityGenLifeActor.h"
#include "CityGenLifeISM.h"
#include "CityGenLifeTypes.h"
#include "Algo/BinarySearch.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "HAL/PlatformTime.h"
#include "MassEntityManager.h"
#include "MassEntitySubsystem.h"
#include "Materials/MaterialInterface.h"
#include "ZoneGraphData.h"
#include "ZoneGraphQuery.h"
#include "ZoneGraphTypes.h"

namespace
{
	FVector UeT(const FVector& C)
	{
		return FVector(C.X * 100.0, -C.Y * 100.0, C.Z * 100.0);
	}

	int32 BandOfT(const int32 Hour)
	{
		const int32 H = ((Hour % 24) + 24) % 24;
		return H < 6 ? 0 : (H < 10 ? 1 : (H < 16 ? 2 : (H < 20 ? 3 : 4)));
	}

	float Smooth01(float X)
	{
		X = FMath::Clamp(X, 0.f, 1.f);
		return X * X * (3.f - 2.f * X);
	}

	// (a line's train, 12 floats: TransitLineCar)
	constexpr int32 CarFloats = 12;
	enum : int32 { CNum = 0, CLen = 1, CGap = 2, CWid = 3, CHgt = 4, CFloor = 5, CBase = 6, CTrack = 7,
		CDoors = 8, CDoorW = 9, CSides = 10, CLevel = 11 };
	// (a part of the model table, 8 floats: TransitParts)
	constexpr int32 PartFloats = 8;
	// (the instances' custom data: base color, emission)
	constexpr int32 TransitData = 6;
	const FTransform HiddenXf(FQuat::Identity, FVector::ZeroVector, FVector::ZeroVector);

	/** A part's colors by its kind (0 body, 1 window, 2 accent, 3 dark; 4 a door leaf, 5 a lit
	 *  doorway) and its line's color: base color and emission (MPC_CityGen's Night lights it). */
	void KindData(const int32 Kind, const FLinearColor& Line, float Out[TransitData])
	{
		FLinearColor Base, Emit = FLinearColor::Black;
		switch (Kind)
		{
		case 0: Base = FMath::Lerp(FLinearColor(0.62f, 0.64f, 0.67f), Line, 0.28f); break;
		case 1: Base = FLinearColor(0.02f, 0.025f, 0.03f); Emit = FLinearColor(1.0f, 0.8f, 0.55f) * 0.035f; break;
		case 2: Base = Line; Emit = Line * 0.2f; break;
		case 4: Base = FMath::Lerp(FLinearColor(0.62f, 0.64f, 0.67f), Line, 0.28f) * 0.7f; break;
		case 5: Base = FLinearColor(0.2f, 0.2f, 0.2f); Emit = FLinearColor(1.0f, 0.85f, 0.65f) * 0.15f; break;
		default: Base = FLinearColor(0.035f, 0.035f, 0.04f); break;
		}
		Out[0] = Base.R; Out[1] = Base.G; Out[2] = Base.B;
		Out[3] = Emit.R; Out[4] = Emit.G; Out[5] = Emit.B;
	}
}

FVector ACityGenLife::FCgTrack::At(double Sm) const
{
	if (P.Num() < 2)
	{
		return P.Num() ? P[0] : FVector::ZeroVector;
	}
	if (bLoop && L > 0.0)
	{
		Sm = FMath::Fmod(Sm, L);
		if (Sm < 0.0)
		{
			Sm += L;
		}
	}
	else
	{
		Sm = FMath::Clamp(Sm, 0.0, L);
	}
	const int32 K = FMath::Clamp((int32)Algo::UpperBound(S, Sm) - 1, 0, P.Num() - 2);
	const double Seg = S[K + 1] - S[K];
	const double T = Seg > 0.0 ? (Sm - S[K]) / Seg : 0.0;
	return P[K] + (P[K + 1] - P[K]) * T;
}

void ACityGenLife::BuildTransit()
{
	const int32 NL = TransitLineMode.Num();
	Tracks.SetNum(NL);
	Trains.Reset();
	LineTrainStart.Init(0, NL + 1);
	for (int32 L = 0; L < NL; ++L)
	{
		FCgTrack& T = Tracks[L];
		T.P.Reset();
		T.S.Reset();
		T.bLoop = TransitLineLoop.IsValidIndex(L) && TransitLineLoop[L] != 0;
		for (int32 P = TransitPointStarts[L]; P < TransitPointStarts[L + 1] && TransitPoints.IsValidIndex(3 * P + 2); ++P)
		{
			T.P.Add(FVector(TransitPoints[3 * P], TransitPoints[3 * P + 1], TransitPoints[3 * P + 2]));
		}
		if (T.bLoop && T.P.Num() > 1)
		{
			const FVector First = T.P[0];      // (a copy: Add may move the array)
			T.P.Add(First);
		}
		double Run = 0.0;
		for (int32 P = 0; P < T.P.Num(); ++P)
		{
			Run += P ? FVector::Dist(T.P[P - 1], T.P[P]) : 0.0;
			T.S.Add(Run);
		}
		T.L = Run;
		int32 Most = 0;
		for (int32 B = 0; B < 5; ++B)
		{
			Most = FMath::Max(Most, TransitLineTrains.IsValidIndex(5 * L + B) ? TransitLineTrains[5 * L + B] : 0);
		}
		const int32 NC = TransitLineCar.IsValidIndex(CarFloats * L) ? FMath::Max(1, (int32)TransitLineCar[CarFloats * L + CNum]) : 1;
		for (int32 K = 0; K < Most; ++K)
		{
			FCgTrain& Tr = Trains.AddDefaulted_GetRef();
			Tr.Line = L;
			Tr.K = K;
			Tr.Cars.Init(FTransform::Identity, NC);
		}
		LineTrainStart[L + 1] = Trains.Num();
	}
	// (one component per mesh of the model table; a run of instances per train in each)
	TransitComps.Reset();
	const int32 NM = TransitMeshes.Num();
	for (int32 M = 0; M < NM; ++M)
	{
		UInstancedStaticMeshComponent* C = NewObject<UCgLifeISM>(this, *FString::Printf(TEXT("TransitMesh%d"), M));
		C->SetMobility(EComponentMobility::Movable);
		C->SetupAttachment(RootComponent);
		C->SetStaticMesh(TransitMeshes[M]);
		if (TransitMaterial)
		{
			for (int32 Sl = 0; Sl < FMath::Max(1, TransitMeshes[M] ? TransitMeshes[M]->GetStaticMaterials().Num() : 1); ++Sl)
			{
				C->SetMaterial(Sl, TransitMaterial);
			}
		}
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCanEverAffectNavigation(false);
		C->SetCastShadow(true);
		C->bAffectDistanceFieldLighting = false;
		C->SetAffectDynamicIndirectLighting(false);
		C->NumCustomDataFloats = TransitData;
		C->RegisterComponent();
		FixBounds(C);
		TransitComps.Add(C);
	}
	TrainInst.SetNum(Trains.Num());
	float Data[TransitData];
	for (int32 I = 0; I < Trains.Num(); ++I)
	{
		FCgTrain& Tr = Trains[I];
		const int32 L = Tr.Line;
		const int32 Mode = TransitLineMode[L];
		const FLinearColor Col = TransitLineColor.IsValidIndex(3 * L + 2)
			? FLinearColor(TransitLineColor[3 * L], TransitLineColor[3 * L + 1], TransitLineColor[3 * L + 2]) : FLinearColor::White;
		TrainInst[I].Init(0, NM);
		const int32 P0 = TransitPartStarts.IsValidIndex(Mode) ? TransitPartStarts[Mode] : 0;
		const int32 P1 = TransitPartStarts.IsValidIndex(Mode + 1) ? TransitPartStarts[Mode + 1] : P0;
		for (int32 M = 0; M < NM; ++M)
		{
			UInstancedStaticMeshComponent* C = TransitComps[M];
			TrainInst[I][M] = C->GetInstanceCount();
			for (int32 Car = 0; Car < Tr.Cars.Num(); ++Car)
			{
				for (int32 P = P0; P < P1; ++P)
				{
					if ((int32)TransitParts[PartFloats * P] != M)
					{
						continue;
					}
					const int32 Inst = C->AddInstance(HiddenXf, false);
					KindData((int32)TransitParts[PartFloats * P + 1], Col, Data);
					C->SetCustomData(Inst, MakeArrayView(Data, TransitData), false);
				}
			}
		}
	}
	// (the door leaves and lit doorways of the trains near the view: a cube's instances,
	// taken as needed)
	DoorComp = nullptr;
	const int32 Cube = 0;
	if (TransitMeshes.IsValidIndex(Cube) && TransitMeshes[Cube])
	{
		UInstancedStaticMeshComponent* C = NewObject<UCgLifeISM>(this, TEXT("TransitDoors"));
		C->SetMobility(EComponentMobility::Movable);
		C->SetupAttachment(RootComponent);
		C->SetStaticMesh(TransitMeshes[Cube]);
		if (TransitMaterial)
		{
			C->SetMaterial(0, TransitMaterial);
		}
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCanEverAffectNavigation(false);
		C->SetCastShadow(false);
		C->bAffectDistanceFieldLighting = false;
		C->SetAffectDynamicIndirectLighting(false);
		C->NumCustomDataFloats = TransitData;
		C->RegisterComponent();
		FixBounds(C);
		DoorComp = C;
	}
	DoorInstUsed = 0;
	// (the platforms' keep-out for the walk processor, cm; the doors that are a served station's
	// street accesses, in the crowd's sorted order)
	WalkClearCm.Init(0.f, WalkLaneCount);
	for (int32 I = 0; I < WalkLaneCount && I < WalkClear.Num(); ++I)
	{
		WalkClearCm[I] = 100.f * FMath::Max(0.f, WalkClear[I]);
	}
	Frame.WalkClear = &WalkClearCm;
	DoorTransitSorted.Init(0, DoorDists.Num());
	for (int32 K = 0; K < DoorTransit.Num() && K < DoorSortedOf.Num(); ++K)
	{
		const int32 Sorted = DoorSortedOf[K];
		if (DoorTransit[K] && DoorTransitSorted.IsValidIndex(Sorted))
		{
			DoorTransitSorted[Sorted] = 1;
		}
	}
	DoorCum.Reset();                       // (the live doors taken again without them)
	TransitRng.Initialize((int32)(GetTypeHash(PlanHash) & 0x7fffffff) ^ 0x51ed);
	for (FCgTrain& Tr : Trains)
	{
		Tr.Sent = -100;
	}
}

float ACityGenLife::LatOf(const int32 L, const int32 Way, const double Sm) const
{
	// (in the train's own frame, + its left: each way on its own right, d off the middle;
	// crossing to the other over TransitCrossM before a turn, so it stands at the end on the
	// track it leaves on)
	const float D = TransitLineCar[CarFloats * L + CTrack];
	if (Tracks[L].bLoop || D <= 0.f)
	{
		return -D;
	}
	const double A = TransitLineTurn[2 * L];
	const double B = TransitLineTurn[2 * L + 1];
	const double X = FMath::Max(1.0, (double)TransitCrossM);
	const double T = Way == 0 ? (Sm - (B - X)) / X : ((A + X) - Sm) / X;
	return -D + 2.f * D * Smooth01((float)T);
}

void ACityGenLife::PlaceTrain(FCgTrain& T, const double Time)
{
	const int32 L = T.Line;
	const float* Car = &TransitLineCar[CarFloats * L];
	const FCgTrack& Tk = Tracks[L];
	const double R = FMath::Max(1.0, (double)TransitLineCycle[L]);
	const int32 N = FMath::Max(1, TransitLineTrains[5 * L + BandOfT(Hour)]);
	T.U = FMath::Fmod(FMath::Max(0.0, Time) + (double)T.K * R / (double)N, R);
	// (the cycle's coordinate at U, between its samples)
	const double Dt = FMath::Max(1.0e-3, (double)TransitLineDt[L]);
	const int32 S0 = TransitSampleStarts[L];
	const int32 NS = TransitSampleStarts[L + 1] - S0;
	const double J = T.U / Dt;
	const int32 K = FMath::Clamp((int32)FMath::FloorToDouble(J), 0, FMath::Max(0, NS - 2));
	const double Fr = FMath::Clamp(J - (double)K, 0.0, 1.0);
	const double C = NS >= 2 ? FMath::Lerp((double)TransitSamples[S0 + K], (double)TransitSamples[S0 + K + 1], Fr) : 0.0;
	const double A = TransitLineTurn[2 * L];
	const double B = TransitLineTurn[2 * L + 1];
	const double D = B - A;
	if (Tk.bLoop || C <= D)
	{
		T.Way = 0;
		T.Sm = A + C;
	}
	else
	{
		T.Way = 1;
		T.Sm = B - (C - D);
	}
	// (the stop event it stands at, its doors)
	T.Event = INDEX_NONE;
	T.Open = 0.f;
	for (int32 E = TransitEventStarts[L]; E < TransitEventStarts[L + 1]; ++E)
	{
		const double Arr = TransitEvents[4 * E];
		const double Dep = TransitEvents[4 * E + 1];
		if (T.U >= Arr && T.U < Dep)
		{
			T.Event = E;
			if (TransitEvents[4 * E + 2] >= 0.f)
			{
				const float Slide = FMath::Max(0.1f, TransitDoorSlideS);
				const float In = (float)(T.U - Arr) - TransitDoorOpenS;
				const float Out = (float)(Dep - T.U) - TransitDoorCloseS;
				T.Open = FMath::Clamp(In / Slide, 0.f, 1.f) * FMath::Clamp(Out / Slide, 0.f, 1.f);
			}
			break;
		}
	}
	// (each car by the track's points at its two ends, on its way's track, its body's bottom
	// at the line's height plus its base)
	const int32 NC = T.Cars.Num();
	const double Dir = (Tk.bLoop || T.Way == 0) ? 1.0 : -1.0;
	const double Len = Car[CLen];
	const double Pitch = Len + Car[CGap];
	FVector Tng = FVector::ForwardVector;
	for (int32 Jc = 0; Jc < NC; ++Jc)
	{
		const double O = ((double)Jc - 0.5 * (double)(NC - 1)) * Pitch;
		const double Sj = T.Sm + Dir * O;
		const FVector Front = Tk.At(Sj + Dir * 0.5 * Len);
		const FVector Back = Tk.At(Sj - Dir * 0.5 * Len);
		const FVector Fw = Front - Back;
		if (Fw.SizeSquared() > 1.0e-6)
		{
			Tng = Fw.GetSafeNormal();
		}
		const FVector Left = FVector(-Tng.Y, Tng.X, 0.0).GetSafeNormal();
		const float Lat = LatOf(L, T.Way, Sj);
		const FVector Pos = 0.5 * (Front + Back) + Left * Lat + FVector(0.0, 0.0, Car[CBase]);
		const FVector FwdUe(Tng.X, -Tng.Y, Tng.Z);
		T.Cars[Jc] = FTransform(FRotationMatrix::MakeFromX(FwdUe).Rotator(), UeT(Pos));
	}
	const FTransform& Mid = T.Cars[NC / 2];
	T.Mid = Mid.GetLocation();
	T.Fwd = Mid.GetRotation().GetForwardVector();
}

bool ACityGenLife::DoorPoint(const FCgTrain& T, const int32 Car, const int32 Door, const float Side, FVector& Out) const
{
	// (a door's middle at the car's floor on a side (+1 its left, -1 its right), UE cm)
	const float* C = &TransitLineCar[CarFloats * T.Line];
	const int32 ND = FMath::Max(1, (int32)C[CDoors]);
	if (!T.Cars.IsValidIndex(Car) || Door < 0 || Door >= ND)
	{
		return false;
	}
	const double X = (((double)Door + 0.5) / (double)ND - 0.5) * C[CLen];
	// (the car's frame in UE: its x forward, y right; a side's citygen left is UE -y)
	const FVector Local(X * 100.0, -Side * (0.5 * C[CWid] + 0.05) * 100.0, (C[CFloor] + 0.05) * 100.0);
	Out = T.Cars[Car].TransformPosition(Local);
	return true;
}

void ACityGenLife::UpdateTransit(const float Dt)
{
	if (!IsTransit() || Trains.Num() == 0)
	{
		return;
	}
	const double T0 = FPlatformTime::Seconds();
	FVector View = Frame.View;
	if (View.IsZero())
	{
		ViewPoint(View);
	}
	const double Time = GetWorld()->GetTimeSeconds();
	const int32 B = BandOfT(Hour);
	TrainsOn = TrainsMoving = TrainsDwelling = TrainsNear = 0;
	for (FCgTrain& T : Trains)
	{
		const bool bWas = T.bOn;
		T.bOn = bTransit && T.K < TransitLineTrains[5 * T.Line + B];
		if (!T.bOn)
		{
			T.Event = INDEX_NONE;
			T.Open = 0.f;
			if (bWas)
			{
				T.Sent = -100;
			}
			continue;
		}
		const int32 Was = T.Event;
		PlaceTrain(T, Time);
		T.bNear = FVector::DistSquared(T.Mid, View) < FMath::Square(100.0 * TransitDoorsM);
		++TrainsOn;
		TrainsNear += T.bNear ? 1 : 0;
		if (T.Event != INDEX_NONE)
		{
			++TrainsDwelling;
			// (a train just halted at a stop: its people leave and board, where its platform
			// is live; one that was there already when the time jumped is left as it is)
			if (T.Event != Was && TransitEvents[4 * T.Event + 2] >= 0.f && T.U - TransitEvents[4 * T.Event] < 2.0 && bWas)
			{
				TrainArrives(T);
			}
		}
		else
		{
			++TrainsMoving;
		}
	}
	DrawTrains();
	DrawDoors();
	++TransitFrame;
	const double Ms = (FPlatformTime::Seconds() - T0) * 1000.0;
	TransitMs = TransitFrame > 1 ? 0.95 * TransitMs + 0.05 * Ms : Ms;
	TransitMsMax = FMath::Max(TransitMsMax * 0.999, Ms);
}

void ACityGenLife::DrawTrains()
{
	// (each train's run of instances in each component: sent every frame near and mid, every
	// fourth past TransitFarM, once when it goes off)
	const FVector View = Frame.View;
	const double Far2 = FMath::Square(100.0 * TransitFarM);
	TArray<FTransform> Xf;
	for (int32 I = 0; I < Trains.Num(); ++I)
	{
		FCgTrain& T = Trains[I];
		const bool bShow = T.bOn && bEnabled;
		if (!bShow && T.Sent == -1)
		{
			continue;
		}
		if (bShow && FVector::DistSquared(T.Mid, View) > Far2 && T.Sent >= 0 && ((TransitFrame + I) % 4) != 0)
		{
			continue;
		}
		const int32 Mode = TransitLineMode[T.Line];
		const int32 P0 = TransitPartStarts.IsValidIndex(Mode) ? TransitPartStarts[Mode] : 0;
		const int32 P1 = TransitPartStarts.IsValidIndex(Mode + 1) ? TransitPartStarts[Mode + 1] : P0;
		for (int32 M = 0; M < TransitComps.Num(); ++M)
		{
			UInstancedStaticMeshComponent* C = TransitComps[M];
			if (!C)
			{
				continue;
			}
			Xf.Reset();
			for (int32 Car = 0; Car < T.Cars.Num(); ++Car)
			{
				for (int32 P = P0; P < P1; ++P)
				{
					const float* Pt = &TransitParts[PartFloats * P];
					if ((int32)Pt[0] != M)
					{
						continue;
					}
					if (!bShow)
					{
						Xf.Add(HiddenXf);
						continue;
					}
					const FTransform Local(FQuat::Identity, FVector(Pt[2] * 100.0, -Pt[3] * 100.0, Pt[4] * 100.0), FVector(Pt[5], Pt[6], Pt[7]));
					Xf.Add(Local * T.Cars[Car]);
				}
			}
			if (Xf.Num())
			{
				C->BatchUpdateInstancesTransforms(TrainInst[I][M], Xf, false, bRebuildRenderState, false);
			}
		}
		T.Sent = bShow ? TransitFrame : -1;
	}
}

void ACityGenLife::DrawDoors()
{
	// (near trains standing at a stop: each door of each car on its open sides as two leaves
	// sliding apart by its doors' opening, a lit doorway between them once open)
	if (!DoorComp)
	{
		return;
	}
	TArray<FTransform> Xf;
	TArray<float> Data;
	float D6[TransitData];
	for (const FCgTrain& T : Trains)
	{
		if (!T.bOn || !T.bNear || !bEnabled || T.Event == INDEX_NONE || TransitEvents[4 * T.Event + 2] < 0.f)
		{
			continue;
		}
		const int32 L = T.Line;
		const float* C = &TransitLineCar[CarFloats * L];
		const FLinearColor Col(TransitLineColor[3 * L], TransitLineColor[3 * L + 1], TransitLineColor[3 * L + 2]);
		const int32 ND = FMath::Max(1, (int32)C[CDoors]);
		const float DW = C[CDoorW];
		const float H = FMath::Min(2.05f, C[CHgt] - C[CFloor] - 0.3f);
		const float Zc = C[CFloor] + 0.5f * H;
		const int32 NSides = (int32)C[CSides];
		for (int32 Car = 0; Car < T.Cars.Num(); ++Car)
		{
			for (int32 Sd = 0; Sd < NSides; ++Sd)
			{
				const float Side = Sd == 0 ? -1.f : 1.f;          // (its right first)
				for (int32 Dr = 0; Dr < ND; ++Dr)
				{
					const float X = (((float)Dr + 0.5f) / (float)ND - 0.5f) * C[CLen];
					const float Y = Side * (0.5f * C[CWid] + 0.035f);
					for (int32 Leaf = 0; Leaf < 2; ++Leaf)
					{
						const float Sg = Leaf == 0 ? -1.f : 1.f;
						const float Cx = X + Sg * (0.25f * DW + T.Open * 0.5f * DW);
						const FTransform Local(FQuat::Identity, FVector(Cx * 100.f, -Y * 100.f, Zc * 100.f), FVector(0.5f * DW, 0.06f, H));
						Xf.Add(Local * T.Cars[Car]);
						KindData(4, Col, D6);
						Data.Append(D6, TransitData);
					}
					if (T.Open > 0.02f)
					{
						const float Yi = Side * (0.5f * C[CWid] + 0.012f);
						const FTransform Local(FQuat::Identity, FVector(X * 100.f, -Yi * 100.f, Zc * 100.f), FVector(DW * T.Open, 0.03f, H));
						Xf.Add(Local * T.Cars[Car]);
						KindData(5, Col, D6);
						Data.Append(D6, TransitData);
					}
				}
			}
		}
	}
	const int32 Need = Xf.Num();
	while (DoorComp->GetInstanceCount() < Need)
	{
		DoorComp->AddInstance(HiddenXf, false);
	}
	for (int32 I = 0; I < Need; ++I)
	{
		DoorComp->SetCustomData(I, MakeArrayView(Data.GetData() + TransitData * I, TransitData), false);
	}
	// (the ones used last frame and not now hidden)
	for (int32 I = Need; I < DoorInstUsed; ++I)
	{
		Xf.Add(HiddenXf);
	}
	if (Xf.Num())
	{
		DoorComp->BatchUpdateInstancesTransforms(0, Xf, false, true, false);
	}
	DoorInstUsed = Need;
	const bool bVis = Need > 0 && bEnabled && bTransit;
	if (DoorComp->IsVisible() != bVis)
	{
		DoorComp->SetVisibility(bVis);
	}
}

void ACityGenLife::TrainArrives(FCgTrain& T)
{
	// (LG3's crowd: the train's people out onto its platform, the platform's into the train)
	if (!IsCity() || !bBuilt)
	{
		return;
	}
	const int32 L = T.Line;
	const int32 E = T.Event;
	const int32 G = TransitStopStarts[L] + (int32)TransitEvents[4 * E + 2];
	if (!TransitStopLane.IsValidIndex(G))
	{
		return;
	}
	const int32 Lane = TransitStopLane[G];
	if (Lane < 0 || Lane >= WalkLaneCount || !InRegion.IsValidIndex(Lane) || !InRegion[Lane])
	{
		return;
	}
	++TransitArrivals;
	const int32 Bd = BandOfT(Hour);
	const float Scale = LiveScale * CrowdScale;
	auto Count = [this](const float X)
	{
		const float F = FMath::Max(0.f, X);
		return (int32)F + (TransitRng.FRand() < F - FMath::FloorToFloat(F) ? 1 : 0);
	};
	int32 NA = Count(TransitStopAlight.IsValidIndex(5 * G + Bd) ? TransitStopAlight[5 * G + Bd] * Scale : 0.f);
	int32 NB = Count(TransitStopBoard.IsValidIndex(5 * G + Bd) ? TransitStopBoard[5 * G + Bd] * Scale : 0.f);
	// (the open doors: each a point on the platform's side, its outward normal; at a stop over
	// the train (a concourse, a pylon sky station's platforms) the point over it at the
	// platform's height)
	const float* C = &TransitLineCar[CarFloats * L];
	const bool bLevel = TransitStopLevel.IsValidIndex(G) && TransitStopLevel[G] != 0;
	const float Zb = TransitStopZ.IsValidIndex(G) ? 100.f * TransitStopZ[G] : 0.f;
	TArray<FVector> Pts, Nrm;
	for (int32 Car = 0; Car < T.Cars.Num(); ++Car)
	{
		for (int32 Sd = 0; Sd < (int32)C[CSides]; ++Sd)
		{
			const float Side = Sd == 0 ? -1.f : 1.f;
			for (int32 Dr = 0; Dr < (int32)C[CDoors]; ++Dr)
			{
				FVector P;
				if (DoorPoint(T, Car, Dr, Side, P))
				{
					const FVector Out = T.Cars[Car].TransformVectorNoScale(FVector(0.0, -Side, 0.0)).GetSafeNormal2D();
					if (!bLevel)
					{
						P.Z = Zb;
					}
					Pts.Add(P);
					Nrm.Add(Out);
				}
			}
		}
	}
	if (Pts.Num() == 0)
	{
		return;
	}
	const double Arr = TransitEvents[4 * E];
	const double Dep = TransitEvents[4 * E + 1];
	const float Wait = FMath::Max(0.f, (float)(Arr + TransitDoorOpenS + 0.6f * TransitDoorSlideS - T.U));
	const float Left = (float)(Dep - T.U) - TransitDoorCloseS - Wait - 1.f;
	FMassEntityManager& EM = GetWorld()->GetSubsystem<UMassEntitySubsystem>()->GetMutableEntityManager();
	const FZoneGraphStorage& S = Lanes->GetStorage();
	// boarding: the crowd on the platform nearest a door on its side, who reach it before the
	// doors shut
	if (NB > 0 && Left > 1.f)
	{
		TArray<TPair<float, int32>> Cand;
		TArray<int32> DoorOf;
		DoorOf.Init(INDEX_NONE, People);
		for (int32 Slot = 0; Slot < People && Slot < Entities.Num(); ++Slot)
		{
			const FCgLifeWalker& W = EM.GetFragmentDataChecked<FCgLifeWalker>(Entities[Slot]);
			if (!W.Active || W.Lane != Lane || W.State != CgWalk::Walk || W.Role != CgRole::Crowd)
			{
				continue;
			}
			float Best = 1.0e9f;
			for (int32 K = 0; K < Pts.Num(); ++K)
			{
				const FVector Rel = W.Pos - Pts[K];
				if (FVector::DotProduct(Rel, Nrm[K]) < -50.0)
				{
					continue;                      // (the door's other side: across the train)
				}
				const float Dd = (float)Rel.Size2D();
				if (Dd < Best)
				{
					Best = Dd;
					DoorOf[Slot] = K;
				}
			}
			if (DoorOf[Slot] != INDEX_NONE && Best < FMath::Min(4500.f, Left * 0.9f * W.Speed))
			{
				Cand.Add({Best, Slot});
			}
		}
		Cand.Sort([](const TPair<float, int32>& A, const TPair<float, int32>& B) { return A.Key < B.Key; });
		TArray<int32> AtDoor;
		AtDoor.Init(0, Pts.Num());
		for (int32 I = 0; I < Cand.Num() && I < NB; ++I)
		{
			const int32 Slot = Cand[I].Value;
			FCgLifeWalker& W = EM.GetFragmentDataChecked<FCgLifeWalker>(Entities[Slot]);
			const int32 K = DoorOf[Slot];
			W.State = CgWalk::Board;
			W.From = W.Pos;
			W.To = bLevel ? Pts[K] - Nrm[K] * 60.0 : FVector(Pts[K].X, Pts[K].Y, W.Pos.Z);
			W.T = -(Wait + 0.7f * (float)AtDoor[K]++);
			W.Next = INDEX_NONE;
			++TransitBoardingNow;
		}
	}
	// leaving: out of its doors in turn, onto the platform walkway beside the door, then on
	const FZoneLaneData& Ln = S.Lanes[Lane];
	const float HW = FMath::Max(50.f, 0.5f * Widths[Lane]);
	for (int32 I = 0; I < NA && FreeSlots.Num(); ++I)
	{
		const int32 K = I % Pts.Num();
		const FVector From = Pts[K] - (bLevel ? Nrm[K] * 40.0 : FVector::ZeroVector);
		// (where along the walkway the door is)
		float Best = 1.0e18f, At = 0.f;
		for (int32 P = Ln.PointsBegin; P + 1 < Ln.PointsEnd; ++P)
		{
			const FVector A = S.LanePoints[P];
			const FVector Bv = S.LanePoints[P + 1];
			const FVector Ab = Bv - A;
			const double L2 = Ab.SizeSquared2D();
			const double Tt = L2 > 0.0 ? FMath::Clamp(((From.X - A.X) * Ab.X + (From.Y - A.Y) * Ab.Y) / L2, 0.0, 1.0) : 0.0;
			const FVector Q = A + Ab * Tt;
			const float Dd = (float)FVector::DistSquared2D(Q, From);
			if (Dd < Best)
			{
				Best = Dd;
				At = S.LanePointProgressions[P] + (float)(FMath::Sqrt(L2) * Tt);
			}
		}
		const float Dir = TransitRng.FRand() < 0.5f ? 1.f : -1.f;
		TArray<int32> Made;
		if (SpawnGroup(Lane, At, Dir, 1, INDEX_NONE, TransitRng, CgRole::Crowd, INDEX_NONE, &Made) == 0 || Made.Num() == 0)
		{
			break;
		}
		FCgLifeWalker& W = EM.GetFragmentDataChecked<FCgLifeWalker>(Entities[Made[0]]);
		FZoneGraphLaneLocation Loc;
		UE::ZoneGraph::Query::CalculateLocationAlongLane(S, Lane, W.Dist, Loc);
		const FVector Right = FVector::CrossProduct(FVector::UpVector, Loc.Direction * W.Dir).GetSafeNormal();
		const float Lat = FMath::Clamp((float)FVector::DotProduct(From - Loc.Position, Right), -0.85f * HW, 0.85f * HW);
		W.Lat = Lat;
		W.Side = FMath::Clamp(Lat / (HW * W.Dir), -0.85f, 0.85f);
		W.ZOff = 0.f;
		W.State = CgWalk::FromSlot;
		W.Slot = INDEX_NONE;
		W.Point = INDEX_NONE;
		W.From = From;
		W.Pos = From;
		W.T = -(Wait + 0.8f * (float)(I / Pts.Num()));
		++TransitAlighted;
	}
}

void ACityGenLife::SetTransit(const bool bOn)
{
	bTransit = bOn;
	for (UInstancedStaticMeshComponent* C : TransitComps)
	{
		if (C)
		{
			C->SetVisibility(bOn && bEnabled);
		}
	}
	if (DoorComp)
	{
		DoorComp->SetVisibility(false);
	}
	if (bBuilt && IsTransit())
	{
		UpdateTransit(0.f);
	}
	// (a served station's street accesses send people out again while transit is off)
	DoorCum.Reset();
}

FString ACityGenLife::TransitStatus() const
{
	if (!IsTransit())
	{
		return TEXT(",\"transit\":null");
	}
	int32 Inst = 0;
	for (const UInstancedStaticMeshComponent* C : TransitComps)
	{
		Inst += C ? C->GetInstanceCount() : 0;
	}
	return FString::Printf(TEXT(",\"transit\":{\"on\":%s,\"hour\":%d,\"lines\":%d,\"trains\":%d,\"running\":%d,\"moving\":%d,\"dwelling\":%d,\"near\":%d,\"arrivals\":%d,\"boarded\":%d,\"boarding\":%d,\"alighted\":%d,\"instances\":%d,\"door_instances\":%d,\"transit_ms\":%.3f,\"transit_ms_max\":%.3f,\"show\":\"%s\"}"),
		bTransit ? TEXT("true") : TEXT("false"), Hour, TransitLineMode.Num(), Trains.Num(), TrainsOn, TrainsMoving, TrainsDwelling, TrainsNear,
		TransitArrivals, TransitBoarded, FMath::Max(0, TransitBoardingNow - TransitBoarded), TransitAlighted, Inst, DoorInstUsed,
		TransitMs, TransitMsMax, *LastTransitShow);
}

bool ACityGenLife::ShowTransit(const FString& What)
{
	if (!bBuilt || !IsTransit())
	{
		return false;
	}
	FVector View;
	if (!ViewPoint(View))
	{
		View = Frame.View;
	}
	// (people boarding or leaving near each train: those walking into its doors or out of them)
	TMap<int32, int32> Busy;
	if (What == TEXT("board") && Entities.Num())
	{
		FMassEntityManager& EM = GetWorld()->GetSubsystem<UMassEntitySubsystem>()->GetMutableEntityManager();
		for (int32 Slot = 0; Slot < People && Slot < Entities.Num(); ++Slot)
		{
			const FCgLifeWalker& W = EM.GetFragmentDataChecked<FCgLifeWalker>(Entities[Slot]);
			if (!W.Active || (W.State != CgWalk::Board && !(W.State == CgWalk::FromSlot && W.Slot == INDEX_NONE)))
			{
				continue;
			}
			for (int32 I = 0; I < Trains.Num(); ++I)
			{
				if (Trains[I].bOn && Trains[I].Event != INDEX_NONE && FVector::DistSquared(Trains[I].Mid, W.Pos) < FMath::Square(6000.0))
				{
					Busy.FindOrAdd(I)++;
				}
			}
		}
	}
	int32 Best = INDEX_NONE;
	double Score = -1.0e18;
	for (int32 I = 0; I < Trains.Num(); ++I)
	{
		const FCgTrain& T = Trains[I];
		if (!T.bOn)
		{
			continue;
		}
		const bool bStop = T.Event != INDEX_NONE && TransitEvents[4 * T.Event + 2] >= 0.f;
		const FString Mode = TransitModes.IsValidIndex(TransitLineMode[T.Line]) ? TransitModes[TransitLineMode[T.Line]] : FString();
		bool bWant;
		double Bonus = 0.0;
		if (What == TEXT("board"))
		{
			const int32 N = Busy.FindRef(I);
			bWant = bStop && T.Open > 0.5f && N > 0;
			Bonus = 2.0e5 * FMath::Min(N, 10);
		}
		else if (What == TEXT("dwell"))
		{
			bWant = bStop && T.Open > 0.5f;
		}
		else if (What == TEXT("moving"))
		{
			bWant = T.Event == INDEX_NONE;
		}
		else
		{
			bWant = T.Event == INDEX_NONE && Mode == What;
		}
		// (within 2 km of the view: the city there is streamed in)
		if (!bWant || FVector::DistSquared(T.Mid, View) > FMath::Square(200000.0))
		{
			continue;
		}
		const double Sc = Bonus - FVector::Dist(T.Mid, View);
		if (Sc > Score)
		{
			Score = Sc;
			Best = I;
		}
	}
	if (Best == INDEX_NONE)
	{
		LastTransitShow = What + TEXT(":none");
		LastShow = LastTransitShow;
		UE_LOG(LogTemp, Display, TEXT("CITYGEN_LIFE_SHOW {\"what\":\"%s\",\"found\":false}"), *What);
		return false;
	}
	const FCgTrain& T = Trains[Best];
	const float* C = &TransitLineCar[CarFloats * T.Line];
	const FString Mode = TransitModes.IsValidIndex(TransitLineMode[T.Line]) ? TransitModes[TransitLineMode[T.Line]] : FString();
	const FTransform& Mid = T.Cars[T.Cars.Num() / 2];
	const FVector Fwd = Mid.GetRotation().GetForwardVector().GetSafeNormal2D();
	const FVector Right = Mid.GetRotation().GetRightVector().GetSafeNormal2D();
	APlayerController* PC = GetWorld()->GetFirstPlayerController();
	APawn* Cam = PC ? PC->GetPawn() : nullptr;
	if (!Cam)
	{
		return false;
	}
	FVector Eye, At;
	// (half the train's length, cm: a camera behind it stands clear of its last car)
	const double Half = 50.0 * ((double)C[CNum] * (C[CLen] + C[CGap]));
	const bool bStop = T.Event != INDEX_NONE && TransitEvents[4 * T.Event + 2] >= 0.f;
	if (bStop)
	{
		// (on its platform, beside the train and back along it, at a standing eye's height,
		// looking at its middle car's door; over it where people board from above)
		const int32 G = TransitStopStarts[T.Line] + (int32)TransitEvents[4 * T.Event + 2];
		const bool bLevel = TransitStopLevel.IsValidIndex(G) && TransitStopLevel[G] != 0;
		const float Zb = TransitStopZ.IsValidIndex(G) ? 100.f * TransitStopZ[G] : (float)T.Mid.Z;
		const double Out = 100.0 * (0.5 * C[CWid] + (Mode == TEXT("sky_tube") ? 6.5 : 4.5));
		FVector Door;
		DoorPoint(T, T.Cars.Num() / 2, 0, -1.f, Door);
		Eye = T.Mid + Right * Out - Fwd * 1400.0;
		Eye.Z = (bLevel ? Door.Z : Zb) + 170.0;
		At = Door + FVector(0.0, 0.0, 100.0);
	}
	else if (Mode == TEXT("metro"))
	{
		// (in its tunnel, behind it between the tracks' rails)
		Eye = T.Mid - Fwd * (Half + 1800.0) + Right * 120.0 + FVector(0.0, 0.0, 220.0);
		At = T.Mid + FVector(0.0, 0.0, 150.0);
	}
	else if (Mode == TEXT("sky_tube"))
	{
		// (beside the tube, level with it)
		Eye = T.Mid - Fwd * (Half * 0.5 + 900.0) + Right * 800.0 + FVector(0.0, 0.0, 150.0);
		At = T.Mid + FVector(0.0, 0.0, 120.0);
	}
	else
	{
		// (beside the line and over it, back along the train)
		Eye = T.Mid - Fwd * (Half + 1500.0) + Right * 2200.0 + FVector(0.0, 0.0, 900.0);
		At = T.Mid + FVector(0.0, 0.0, 150.0);
	}
	Cam->SetActorLocation(Eye, false, nullptr, ETeleportType::TeleportPhysics);
	PC->SetControlRotation((At - Eye).Rotation());
	const FString Id = TransitLineIds.IsValidIndex(T.Line) ? FString::Printf(TEXT("train.%s.%d"), *TransitLineIds[T.Line], T.K) : FString::FromInt(Best);
	LastTransitShow = What + TEXT(":") + Id;
	LastShow = LastTransitShow;
	const FVector P = T.Mid / 100.0;
	UE_LOG(LogTemp, Display, TEXT("CITYGEN_LIFE_SHOW {\"what\":\"%s\",\"found\":true,\"train\":\"%s\",\"at\":[%.1f,%.1f,%.1f],\"open\":%.2f,\"event\":%d,\"busy\":%d}"),
		*What, *Id, P.X, -P.Y, P.Z, T.Open, T.Event, Busy.FindRef(Best));
	return true;
}
