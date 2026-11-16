// lifegen's air and water (LG7): see CityGenLifeActor.h ("LG7: air and water") and
// docs/unreal_export.md ("From LG7: air and water").
//
// Everything that flies or floats runs a route by the world's time, as LG6's trains run their
// lines: a vehicle's place along its route is the route's sampled cycle at (time + its phase)
// modulo the cycle, the hour band's vehicles evenly round it, so nothing is simulated and a
// vehicle far off costs a lookup (its instances sent every fourth frame past AwFarM). Its
// heading is the route's at that point (a double-ended ferry's or a ship backing out of its
// berth stern first); a flier banks into its turns by its turn rate and speed and pitches with
// its climb, a boat rolls and bobs. Its parts are instances of one component per mesh and cull
// distance: AG18's hover cars' meshes in their vehicle's paint, the stand-ins' basic shapes in
// M_CgTransit (base color and emission from the part's kind and the route's color), the
// flashing ones (strobes, beacons, police bars) drawn only while lit.

#include "CityGenLifeActor.h"
#include "Algo/BinarySearch.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "HAL/PlatformTime.h"
#include "Materials/MaterialInterface.h"

namespace
{
	int32 BandOfA(const int32 Hour)
	{
		const int32 H = ((Hour % 24) + 24) % 24;
		return H < 6 ? 0 : (H < 10 ? 1 : (H < 16 ? 2 : (H < 20 ? 3 : 4)));
	}

	// (a part of the model table, 9 floats: AwParts)
	constexpr int32 AwPartFloats = 9;
	constexpr int32 AwStandIn = 6;
	constexpr int32 AwPainted = 9;
	const FTransform AwHidden(FQuat::Identity, FVector::ZeroVector, FVector::ZeroVector);
	// (the kinds, as presets.AW_KINDS: the first six fly)
	constexpr int32 AwAirKinds = 6;
	const float BankMax[10] = {22.f, 12.f, 18.f, 10.f, 25.f, 20.f, 0.f, 0.f, 0.f, 0.f};
	const float RollAmp[10] = {0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 1.6f, 1.2f, 0.5f, 0.25f};
	const float BobAmp[10] = {0.f, 0.f, 0.f, 0.f, 0.f, 0.f, 0.05f, 0.05f, 0.03f, 0.02f};
	const float ShowDist[10] = {12.f, 3.f, 14.f, 22.f, 160.f, 140.f, 14.f, 20.f, 48.f, 170.f};

	/** A stand-in part's colors by its kind (0 body, 1 window, 2 accent, 3 dark, 4 nav red, 5 nav
	 *  green, 6 strobe, 7 police red, 8 police blue, 9 lamp, 10 hull, 11 beacon) and its route's
	 *  color: base color and emission (MPC_CityGen's Night brightens it). */
	void AwKindData(const int32 Kind, const FLinearColor& Col, float Out[AwStandIn])
	{
		FLinearColor Base = FLinearColor(0.035f, 0.035f, 0.04f), Emit = FLinearColor::Black;
		switch (Kind)
		{
		case 0: Base = FMath::Lerp(FLinearColor(0.6f, 0.62f, 0.65f), Col, 0.35f); break;
		case 1: Base = FLinearColor(0.02f, 0.025f, 0.03f); Emit = FLinearColor(1.0f, 0.8f, 0.55f) * 0.05f; break;
		case 2: Base = Col; Emit = Col * 1.2f; break;
		case 4: Base = FLinearColor(0.3f, 0.01f, 0.01f); Emit = FLinearColor(1.0f, 0.04f, 0.02f) * 3.f; break;
		case 5: Base = FLinearColor(0.01f, 0.3f, 0.05f); Emit = FLinearColor(0.05f, 1.0f, 0.25f) * 3.f; break;
		case 6: Base = FLinearColor(0.8f, 0.8f, 0.8f); Emit = FLinearColor(1.0f, 1.0f, 1.0f) * 6.f; break;
		case 7: Base = FLinearColor(0.4f, 0.02f, 0.02f); Emit = FLinearColor(1.0f, 0.03f, 0.03f) * 7.f; break;
		case 8: Base = FLinearColor(0.02f, 0.05f, 0.4f); Emit = FLinearColor(0.05f, 0.18f, 1.0f) * 7.f; break;
		case 9: Base = FLinearColor(0.8f, 0.8f, 0.75f); Emit = FLinearColor(1.0f, 0.95f, 0.85f) * 2.f; break;
		case 10: Base = Col; break;
		case 11: Base = FLinearColor(0.4f, 0.02f, 0.02f); Emit = FLinearColor(1.0f, 0.05f, 0.03f) * 6.f; break;
		default: break;
		}
		Out[0] = Base.R; Out[1] = Base.G; Out[2] = Base.B;
		Out[3] = Emit.R; Out[4] = Emit.G; Out[5] = Emit.B;
	}

	/** Whether a flashing part is lit at time T (its vehicle's phase P). */
	bool Lit(const int32 Kind, const double T, const double P)
	{
		switch (Kind)
		{
		case 6: return FMath::Fmod(T + P, 1.2) < 0.09;
		case 7: return FMath::Fmod(T + P, 0.8) < 0.4;
		case 8: return FMath::Fmod(T + P, 0.8) >= 0.4;
		case 11: return FMath::Fmod(T + P, 1.6) < 0.2;
		default: return true;
		}
	}

	float WrapDeg(float D)
	{
		D = FMath::Fmod(D + 180.f, 360.f);
		if (D < 0.f)
		{
			D += 360.f;
		}
		return D - 180.f;
	}
}

double ACityGenLife::AwSampleAt(const int32 R, double U) const
{
	const double Cyc = FMath::Max(1.0e-3, (double)AwRouteCycle[R]);
	U = FMath::Fmod(U, Cyc);
	if (U < 0.0)
	{
		U += Cyc;
	}
	const double Dt = FMath::Max(1.0e-3, (double)AwRouteDt[R]);
	const int32 S0 = AwSampleStarts[R];
	const int32 NS = AwSampleStarts[R + 1] - S0;
	if (NS < 2)
	{
		return 0.0;
	}
	const double J = U / Dt;
	const int32 K = FMath::Clamp((int32)FMath::FloorToDouble(J), 0, NS - 2);
	const double Fr = FMath::Clamp(J - (double)K, 0.0, 1.0);
	return FMath::Lerp((double)AwSamples[S0 + K], (double)AwSamples[S0 + K + 1], Fr);
}

void ACityGenLife::AwPathAt(const int32 R, double Sm, FVector& Pos, float& YawDeg) const
{
	const TArray<double>& S = AwCum[R];
	const int32 P0 = AwPointStarts[R];
	const int32 N = AwPointStarts[R + 1] - P0;
	if (N < 2 || S.Num() != N)
	{
		Pos = N ? FVector(AwPoints[4 * P0], AwPoints[4 * P0 + 1], AwPoints[4 * P0 + 2]) : FVector::ZeroVector;
		YawDeg = N ? AwPoints[4 * P0 + 3] : 0.f;
		return;
	}
	const double L = S.Last();
	if (L > 0.0)
	{
		Sm = FMath::Fmod(Sm, L);
		if (Sm < 0.0)
		{
			Sm += L;
		}
	}
	const int32 K = FMath::Clamp((int32)Algo::UpperBound(S, Sm) - 1, 0, N - 2);
	const double Seg = S[K + 1] - S[K];
	const double T = Seg > 0.0 ? (Sm - S[K]) / Seg : 0.0;
	const float* A = &AwPoints[4 * (P0 + K)];
	const float* B = &AwPoints[4 * (P0 + K + 1)];
	Pos = FVector(A[0] + (B[0] - A[0]) * T, A[1] + (B[1] - A[1]) * T, A[2] + (B[2] - A[2]) * T);
	YawDeg = A[3] + WrapDeg(B[3] - A[3]) * (float)T;
}

void ACityGenLife::BuildAirWater()
{
	const int32 NR = AwRouteKind.Num();
	AwCum.SetNum(NR);
	AwVehicles.Reset();
	for (int32 R = 0; R < NR; ++R)
	{
		TArray<double>& S = AwCum[R];
		S.Reset();
		double Run = 0.0;
		for (int32 P = AwPointStarts[R]; P < AwPointStarts[R + 1] && AwPoints.IsValidIndex(4 * P + 3); ++P)
		{
			if (P > AwPointStarts[R])
			{
				const float* A = &AwPoints[4 * (P - 1)];
				const float* B = &AwPoints[4 * P];
				Run += FVector::Dist(FVector(A[0], A[1], A[2]), FVector(B[0], B[1], B[2]));
			}
			S.Add(Run);
		}
		int32 Most = 0;
		for (int32 B = 0; B < 5; ++B)
		{
			Most = FMath::Max(Most, AwRouteCount.IsValidIndex(5 * R + B) ? AwRouteCount[5 * R + B] : 0);
		}
		for (int32 K = 0; K < Most; ++K)
		{
			FCgAwVehicle& V = AwVehicles.AddDefaulted_GetRef();
			V.Route = R;
			V.K = K;
			V.bAir = AwRouteKind[R] < AwAirKinds;
			const int32 Pi = AwPaintStarts.IsValidIndex(R + 1) ? AwPaintStarts[R] + K : INDEX_NONE;
			V.Paint = (Pi != INDEX_NONE && Pi < AwPaintStarts[R + 1]) ? Pi : INDEX_NONE;
		}
	}
	// (one component per mesh and cull distance; each vehicle's parts an instance in theirs)
	AwComps.Reset();
	AwXf.Reset();
	AwVehPartStart.Reset();
	AwPartComp.Reset();
	AwPartInst.Reset();
	AwPartIdx.Reset();
	TMap<int64, int32> CompOf;
	TArray<TArray<float>> Data;
	for (const FCgAwVehicle& V : AwVehicles)
	{
		AwVehPartStart.Add(AwPartComp.Num());
		const int32 M = AwRouteModel[V.Route];
		const int32 P0 = AwModelPartStarts.IsValidIndex(M) ? AwModelPartStarts[M] : 0;
		const int32 P1 = AwModelPartStarts.IsValidIndex(M + 1) ? AwModelPartStarts[M + 1] : P0;
		const FLinearColor Col(AwRouteColor[3 * V.Route], AwRouteColor[3 * V.Route + 1], AwRouteColor[3 * V.Route + 2]);
		for (int32 P = P0; P < P1; ++P)
		{
			const float* Pt = &AwParts[AwPartFloats * P];
			const int32 Mesh = (int32)Pt[0];
			if (!AwMeshes.IsValidIndex(Mesh) || !AwMeshes[Mesh])
			{
				continue;
			}
			const int64 Key = (int64)Mesh * 100000 + (int64)FMath::RoundToInt(Pt[8]);
			int32* Found = CompOf.Find(Key);
			int32 C;
			if (Found)
			{
				C = *Found;
			}
			else
			{
				const int32 Floats = AwMeshFloats.IsValidIndex(Mesh) ? AwMeshFloats[Mesh] : AwStandIn;
				UInstancedStaticMeshComponent* Comp = NewObject<UInstancedStaticMeshComponent>(this, *FString::Printf(TEXT("AirWater%d"), AwComps.Num()));
				Comp->SetMobility(EComponentMobility::Movable);
				Comp->SetupAttachment(RootComponent);
				Comp->SetStaticMesh(AwMeshes[Mesh]);
				if (Floats == AwStandIn && AwMaterial)
				{
					for (int32 Sl = 0; Sl < FMath::Max(1, AwMeshes[Mesh]->GetStaticMaterials().Num()); ++Sl)
					{
						Comp->SetMaterial(Sl, AwMaterial);
					}
				}
				Comp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
				Comp->SetCanEverAffectNavigation(false);
				Comp->SetCastShadow(false);
				Comp->bAffectDistanceFieldLighting = false;
				Comp->SetAffectDynamicIndirectLighting(false);
				Comp->NumCustomDataFloats = Floats;
				if (Pt[8] > 0.f)
				{
					Comp->SetCullDistances(0, (int32)(100.f * Pt[8]));
				}
				Comp->RegisterComponent();
				C = AwComps.Add(Comp);
				AwXf.AddDefaulted();
				Data.AddDefaulted();
				CompOf.Add(Key, C);
			}
			AwPartComp.Add(C);
			AwPartInst.Add(AwXf[C].Num());
			AwPartIdx.Add(P);
			AwXf[C].Add(AwHidden);
			const int32 Floats = AwComps[C]->NumCustomDataFloats;
			if (Floats == AwPainted)
			{
				const float* Pa = (V.Paint != INDEX_NONE && AwPaints.IsValidIndex(9 * V.Paint + 8)) ? &AwPaints[9 * V.Paint] : nullptr;
				for (int32 F = 0; F < AwPainted; ++F)
				{
					Data[C].Add(Pa ? Pa[F] : 0.35f);
				}
			}
			else
			{
				float D6[AwStandIn];
				AwKindData((int32)Pt[1], Col, D6);
				Data[C].Append(D6, AwStandIn);
			}
		}
	}
	AwVehPartStart.Add(AwPartComp.Num());
	for (int32 C = 0; C < AwComps.Num(); ++C)
	{
		UInstancedStaticMeshComponent* Comp = AwComps[C];
		Comp->AddInstances(AwXf[C], false);
		const int32 Floats = Comp->NumCustomDataFloats;
		for (int32 I = 0; I < AwXf[C].Num(); ++I)
		{
			Comp->SetCustomData(I, MakeArrayView(Data[C].GetData() + Floats * I, Floats), false);
		}
		Comp->MarkRenderStateDirty();
		Comp->SetVisibility(bEnabled);
	}
	for (FCgAwVehicle& V : AwVehicles)
	{
		V.Sent = -100;
	}
}

void ACityGenLife::PlaceAw(FCgAwVehicle& V, const double Time)
{
	const int32 R = V.Route;
	const int32 Kind = AwRouteKind[R];
	const double Cyc = FMath::Max(1.0, (double)AwRouteCycle[R]);
	const int32 N = FMath::Max(1, AwRouteCount[5 * R + BandOfA(Hour)]);
	V.U = FMath::Fmod(FMath::Max(0.0, Time) + (double)V.K * Cyc / (double)N, Cyc);
	V.Sm = AwSampleAt(R, V.U);
	const double L = AwCum[R].Num() ? AwCum[R].Last() : 0.0;
	double Ds = AwSampleAt(R, V.U + 0.5) - AwSampleAt(R, V.U - 0.5);
	if (L > 0.0 && Ds < -0.5 * L)
	{
		Ds += L;
	}
	V.Speed = (float)FMath::Max(0.0, Ds);
	V.Event = INDEX_NONE;
	for (int32 E = AwEventStarts[R]; E < AwEventStarts[R + 1]; ++E)
	{
		if (V.U >= AwEvents[3 * E] && V.U < AwEvents[3 * E + 1])
		{
			V.Event = E;
			break;
		}
	}
	FVector Pos;
	float Yaw;
	AwPathAt(R, V.Sm, Pos, Yaw);
	float Bank = 0.f, Pitch = 0.f, Roll = 0.f;
	const double Ph = 0.137 * (double)(R * 7 + V.K * 3);
	if (Kind < AwAirKinds)
	{
		// (a flier banks by its turn rate and speed, pitches with its climb in plan)
		const double D = FMath::Max(1.5, 0.6 * (double)V.Speed);
		FVector PA, PB;
		float YA, YB;
		AwPathAt(R, V.Sm - D, PA, YA);
		AwPathAt(R, V.Sm + D, PB, YB);
		if (V.Speed > 1.f)
		{
			const float Rate = WrapDeg(YB - YA) / (float)(2.0 * D / FMath::Max(0.1f, V.Speed));
			Bank = FMath::Clamp(FMath::RadiansToDegrees(FMath::Atan(V.Speed * FMath::DegreesToRadians(Rate) / 9.81f)), -BankMax[Kind], BankMax[Kind]);
			const double Dh = FVector::Dist2D(PA, PB);
			if (Dh > D)
			{
				Pitch = FMath::Clamp(0.5f * FMath::RadiansToDegrees(FMath::Atan2((float)(PB.Z - PA.Z), (float)Dh)), -8.f, 8.f);
			}
		}
		Roll = -Bank;
	}
	else
	{
		// (a boat rolls and bobs on the water)
		Roll = RollAmp[Kind] * (float)FMath::Sin(0.9 * Time + Ph);
		Pitch = 0.5f * RollAmp[Kind] * (float)FMath::Sin(0.7 * Time + 1.7 * Ph);
		Pos.Z += BobAmp[Kind] * FMath::Sin(1.3 * Time + 2.3 * Ph);
	}
	V.Xf = FTransform(FRotator(Pitch, -Yaw, Roll), FVector(Pos.X * 100.0, -Pos.Y * 100.0, Pos.Z * 100.0));
}

void ACityGenLife::UpdateAirWater(const float Dt)
{
	if (!IsAirWater() || AwVehicles.Num() == 0)
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
	const int32 B = BandOfA(Hour);
	const double Far2 = FMath::Square(100.0 * AwFarM);
	AwAirOn = AwWaterOn = AwDwelling = AwNear = 0;
	TArray<uint8> Dirty;
	Dirty.Init(0, AwComps.Num());
	for (int32 I = 0; I < AwVehicles.Num(); ++I)
	{
		FCgAwVehicle& V = AwVehicles[I];
		const bool bOn = bEnabled && (V.bAir ? bAir : bWater) && V.K < AwRouteCount[5 * V.Route + B];
		const int32 Q0 = AwVehPartStart[I];
		const int32 Q1 = AwVehPartStart[I + 1];
		if (!bOn)
		{
			if (V.Sent != -1)
			{
				for (int32 Q = Q0; Q < Q1; ++Q)
				{
					AwXf[AwPartComp[Q]][AwPartInst[Q]] = AwHidden;
					Dirty[AwPartComp[Q]] = 1;
				}
				V.Sent = -1;
				V.Event = INDEX_NONE;
			}
			continue;
		}
		const bool bFar = FVector::DistSquared(V.Xf.GetLocation(), View) > Far2;
		(V.bAir ? AwAirOn : AwWaterOn) += 1;
		AwNear += bFar ? 0 : 1;
		if (bFar && V.Sent >= 0 && ((AwFrame + I) % 4) != 0)
		{
			AwDwelling += V.Event != INDEX_NONE ? 1 : 0;
			continue;
		}
		PlaceAw(V, Time);
		AwDwelling += V.Event != INDEX_NONE ? 1 : 0;
		const double Ph = 0.137 * (double)(V.Route * 7 + V.K * 3);
		for (int32 Q = Q0; Q < Q1; ++Q)
		{
			const float* Pt = &AwParts[AwPartFloats * AwPartIdx[Q]];
			const int32 Kind = (int32)Pt[1];
			FTransform& X = AwXf[AwPartComp[Q]][AwPartInst[Q]];
			if (Kind >= 0 && !Lit(Kind, Time, Ph))
			{
				X = AwHidden;
			}
			else
			{
				const FTransform Local(FQuat::Identity, FVector(Pt[2] * 100.0, -Pt[3] * 100.0, Pt[4] * 100.0), FVector(Pt[5], Pt[6], Pt[7]));
				X = Local * V.Xf;
			}
			Dirty[AwPartComp[Q]] = 1;
		}
		V.Sent = AwFrame;
	}
	for (int32 C = 0; C < AwComps.Num(); ++C)
	{
		if (Dirty[C] && AwComps[C] && AwXf[C].Num())
		{
			AwComps[C]->BatchUpdateInstancesTransforms(0, AwXf[C], false, bRebuildRenderState, false);
		}
	}
	++AwFrame;
	const double Ms = (FPlatformTime::Seconds() - T0) * 1000.0;
	AwMs = AwFrame > 1 ? 0.95 * AwMs + 0.05 * Ms : Ms;
	AwMsMax = FMath::Max(AwMsMax * 0.999, Ms);
}

void ACityGenLife::SetAir(const bool bOn)
{
	bAir = bOn;
	if (bBuilt && IsAirWater())
	{
		UpdateAirWater(0.f);
	}
}

void ACityGenLife::SetWater(const bool bOn)
{
	bWater = bOn;
	if (bBuilt && IsAirWater())
	{
		UpdateAirWater(0.f);
	}
}

FString ACityGenLife::AirWaterStatus() const
{
	if (!IsAirWater())
	{
		return TEXT(",\"airwater\":null");
	}
	int32 Inst = 0;
	for (const UInstancedStaticMeshComponent* C : AwComps)
	{
		Inst += C ? C->GetInstanceCount() : 0;
	}
	return FString::Printf(TEXT(",\"airwater\":{\"air\":%s,\"water\":%s,\"hour\":%d,\"routes\":%d,\"vehicles\":%d,\"air_on\":%d,\"water_on\":%d,\"dwelling\":%d,\"near\":%d,\"components\":%d,\"instances\":%d,\"aw_ms\":%.3f,\"aw_ms_max\":%.3f,\"show\":\"%s\"}"),
		bAir ? TEXT("true") : TEXT("false"), bWater ? TEXT("true") : TEXT("false"), Hour, AwRouteKind.Num(), AwVehicles.Num(),
		AwAirOn, AwWaterOn, AwDwelling, AwNear, AwComps.Num(), Inst, AwMs, AwMsMax, *LastAwShow);
}

bool ACityGenLife::ShowAirWater(const FString& What)
{
	if (!bBuilt || !IsAirWater())
	{
		return false;
	}
	FVector View;
	if (!ViewPoint(View))
	{
		View = Frame.View;
	}
	const double Time = GetWorld()->GetTimeSeconds();
	const int32 KCar = AwKinds.IndexOfByKey(TEXT("car"));
	int32 Best = INDEX_NONE;
	double Score = -1.0e18;
	double PadU = 0.0;
	for (int32 I = 0; I < AwVehicles.Num(); ++I)
	{
		FCgAwVehicle& V = AwVehicles[I];
		if (V.Sent < 0)
		{
			continue;
		}
		PlaceAw(V, Time);
		const int32 Kind = AwRouteKind[V.Route];
		const FString KName = AwKinds.IsValidIndex(Kind) ? AwKinds[Kind] : FString();
		bool bWant = false;
		double Bonus = 0.0;
		double Arr = 0.0;
		if (What == TEXT("landing"))
		{
			// (a car coming down onto its pad: its next pad dwell 2 to 9 s off, over it)
			if (Kind == KCar && V.Event == INDEX_NONE)
			{
				for (int32 E = AwEventStarts[V.Route]; E < AwEventStarts[V.Route + 1]; ++E)
				{
					const double Dt = AwEvents[3 * E] - V.U;
					if (AwEvents[3 * E + 2] == 0.f && Dt > 2.0 && Dt < 9.0)
					{
						bWant = true;
						Arr = AwEvents[3 * E];
					}
				}
			}
		}
		else if (What == TEXT("pier"))
		{
			bWant = V.Event != INDEX_NONE && (KName == TEXT("taxi") || KName == TEXT("ferry"));
		}
		else if (What == TEXT("layers"))
		{
			bWant = Kind == KCar && V.Event == INDEX_NONE && AwRouteIds[V.Route].StartsWith(TEXT("air.lane."));
			Bonus = 0.0;
		}
		else
		{
			bWant = KName == What;
			Bonus = V.Event == INDEX_NONE ? 5.0e4 : 0.0;
		}
		// (within 3 km of the view: the city there is streamed in; an aircraft anywhere)
		const double D = FVector::Dist(V.Xf.GetLocation(), View);
		if (!bWant || (D > 300000.0 && KName != TEXT("aircraft") && KName != TEXT("shuttle")))
		{
			continue;
		}
		const double Sc = Bonus - D;
		if (Sc > Score)
		{
			Score = Sc;
			Best = I;
			PadU = Arr;
		}
	}
	APlayerController* PC = GetWorld()->GetFirstPlayerController();
	APawn* Cam = PC ? PC->GetPawn() : nullptr;
	if (Best == INDEX_NONE || !Cam)
	{
		LastAwShow = What + TEXT(":none");
		LastShow = LastAwShow;
		UE_LOG(LogTemp, Display, TEXT("CITYGEN_LIFE_SHOW {\"what\":\"%s\",\"found\":false}"), *What);
		return false;
	}
	const FCgAwVehicle& V = AwVehicles[Best];
	const int32 Kind = AwRouteKind[V.Route];
	const FVector P = V.Xf.GetLocation();
	const FVector Fwd = V.Xf.GetRotation().GetForwardVector().GetSafeNormal2D();
	const FVector Right = FVector::CrossProduct(FVector::UpVector, Fwd).GetSafeNormal();
	const double Dd = 100.0 * ShowDist[FMath::Clamp(Kind, 0, 9)];
	FVector Eye, At;
	if (What == TEXT("landing"))
	{
		// (beside the pad, a little over its roof, the car coming down onto it in the frame)
		FVector Pad;
		float Yw;
		AwPathAt(V.Route, AwSampleAt(V.Route, PadU), Pad, Yw);
		const FVector PadUe(Pad.X * 100.0, -Pad.Y * 100.0, Pad.Z * 100.0);
		FVector Side = FVector::CrossProduct(FVector::UpVector, (P - PadUe).GetSafeNormal2D());
		if (Side.IsNearlyZero())
		{
			Side = Right;
		}
		Eye = PadUe + Side * 1600.0 + FVector(0.0, 0.0, 450.0);
		At = 0.5 * (PadUe + P);
	}
	else if (What == TEXT("layers"))
	{
		// (behind and over a car on a circuit, along its way: the cars ahead on its layer)
		Eye = P - Fwd * 3000.0 + Right * 900.0 + FVector(0.0, 0.0, 700.0);
		At = P + Fwd * 12000.0;
	}
	else if (Kind >= AwAirKinds)
	{
		Eye = P - Fwd * Dd + Right * Dd * 0.6 + FVector(0.0, 0.0, Dd * 0.35 + 200.0);
		At = P + FVector(0.0, 0.0, 150.0);
	}
	else
	{
		Eye = P - Fwd * Dd + Right * Dd * 0.5 + FVector(0.0, 0.0, Dd * 0.25);
		At = P;
	}
	Cam->SetActorLocation(Eye, false, nullptr, ETeleportType::TeleportPhysics);
	PC->SetControlRotation((At - Eye).Rotation());
	const FString Id = AwRouteIds.IsValidIndex(V.Route) ? FString::Printf(TEXT("%s.%d"), *AwRouteIds[V.Route], V.K) : FString::FromInt(Best);
	LastAwShow = What + TEXT(":") + Id;
	LastShow = LastAwShow;
	UE_LOG(LogTemp, Display, TEXT("CITYGEN_LIFE_SHOW {\"what\":\"%s\",\"found\":true,\"vehicle\":\"%s\",\"at\":[%.1f,%.1f,%.1f],\"speed\":%.1f,\"event\":%d}"),
		*What, *Id, P.X / 100.0, -P.Y / 100.0, P.Z / 100.0, V.Speed, V.Event);
	return true;
}
