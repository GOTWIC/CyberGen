// lifegen's hour, weather and reactions (LG8): see CityGenLifeActor.h ("LG8: the hour, the
// weather and reactions") and docs/unreal_export.md ("From LG8").
//
// Life follows atmosgen's controller (ACityGenAtmos, found by its class's name: no link between
// the plugins, as the play features find it): its Hour every half second (a step of an hour as
// time runs: the doors' and places' rates and the live walkways' and lanes' numbers move, people
// go in and come out over their trips; a jump, a menu's day or night: every live walkway and
// lane filled again at the new hour), its weather state (GetWeatherLabel, the state it turns to)
// and its rain (RainRate while bRain): the plan's table by state gives people out, their pace,
// raincoats and umbrellas, the chance to shelter, the cars' share, speed and headway; a rain
// state's values are reached by its rain, so they follow atmosgen's change of state as its rain
// does. Umbrellas: two instanced components (a canopy and a shaft, the engine's basic shapes in
// the trains' material) of the near and mid people who hold one. umbrella_hold: held in the right
// hand, the arm up (near, the group's held arm layered over the clip, UCgPersonAnim; mid, the
// bake's loops with the arm held and the umbrella at the bake's grip); under a cover a near
// person lowers the arm and the umbrella hangs furled from the hand, a mid one's is not drawn.
// Without the held arm's data, LG8's over the right shoulder. A danger (Panic) is the
// processor's (CgLife::StepCity).

#include "CityGenLifeActor.h"
#include "CityGenLifeAnim.h"
#include "Animation/AnimSequence.h"
#include "Animation/Skeleton.h"
#include "Components/SkeletalMeshComponent.h"
#include "ProfilingDebugging/CpuProfilerTrace.h"
#include "CityGenLifeISM.h"
#include "CityGenLifeTypes.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "MassEntityManager.h"
#include "MassEntitySubsystem.h"
#include "UObject/UnrealType.h"

namespace
{
	constexpr float AtmosStep = 0.5f;     // s between reads of atmosgen's hour and weather
	constexpr float ThinStep = 2.f;       // s between sending some people in when too many are out
	const FTransform HiddenXf(FQuat::Identity, FVector(0.0, 0.0, -1.0e6), FVector(0.0));

	uint32 MixW(uint32 X)
	{
		X ^= X >> 16; X *= 0x7feb352du; X ^= X >> 15; X *= 0x846ca68bu; X ^= X >> 16;
		return X;
	}
}

void ACityGenLife::BuildWeather()
{
	// (the stretches out of the rain in cm, as the lanes' distances)
	const int32 N = WalkLaneCount;
	CoverStartsG.Reset();
	CoverCm.Reset();
	if (WalkCoverStarts.Num() == N + 1)
	{
		CoverStartsG = WalkCoverStarts;
		CoverCm.Reserve(WalkCover.Num());
		for (const float V : WalkCover)
		{
			CoverCm.Add(100.f * V);
		}
	}
	WalkCovered.Init(0, FMath::Max(People, PersonChar.Num()));
	Frame.CoverStarts = CoverStartsG.Num() ? &CoverStartsG : nullptr;
	Frame.Cover = &CoverCm;
	Frame.Covered = &WalkCovered;
	Frame.RoadSide = WalkRoadSide.Num() == N ? &WalkRoadSide : nullptr;
	Frame.ShelterS = ShelterS;
	Frame.bLook = bLook;
	Frame.LookCm = 100.f * LookM;
	Frame.FleeMul = FMath::Max(1.f, FleePace);
	Frame.bGather = bGather;
	Frame.GatherCm = 100.f * GatherM;
	Frame.GatherShare = GatherShare;
	Frame.RingCm = RingM * 100.0;
	Frame.StayS = StayS;
	Frame.StuckS = StuckS;
	Frame.StuckFarCm = 100.f * StuckFarM;
	WeatherState = WeatherPlan.IsEmpty() ? FString(TEXT("clear")) : WeatherPlan;
	RainNow = WeatherRain.IsValidIndex(WeatherNames.IndexOfByKey(WeatherState)) ? WeatherRain[WeatherNames.IndexOfByKey(WeatherState)] : 0.f;
	ApplyWeatherNow();
	MakeUmbrellas();
}

float ACityGenLife::WeatherKey(const int32 State, const TCHAR* Key) const
{
	const int32 K = WeatherKeys.IndexOfByKey(FString(Key));
	const int32 NK = WeatherKeys.Num();
	if (K == INDEX_NONE || !WeatherLife.IsValidIndex(State * NK + K))
	{
		return FCString::Strcmp(Key, TEXT("headway_s")) == 0 ? 0.f : (FCString::Strcmp(Key, TEXT("rain_looks")) == 0 ||
			FCString::Strcmp(Key, TEXT("umbrella")) == 0 || FCString::Strcmp(Key, TEXT("shelter")) == 0 ? 0.f : 1.f);
	}
	return WeatherLife[State * NK + K];
}

void ACityGenLife::ApplyWeatherNow()
{
	if (!IsWeather())
	{
		return;
	}
	const FString State = bWeatherOn ? WeatherState : FString(TEXT("clear"));
	const int32 Clear = FMath::Max(0, WeatherNames.IndexOfByKey(FString(TEXT("clear"))));
	int32 S = WeatherNames.IndexOfByKey(State);
	if (S == INDEX_NONE)
	{
		S = Clear;
	}
	// (a rain state's values by its rain now over the state's own: they follow a change of
	// state as atmosgen's rain does; the other states' at once)
	const float StateRain = WeatherRain.IsValidIndex(S) ? WeatherRain[S] : 0.f;
	const float W = StateRain > 0.f ? FMath::Clamp((bWeatherOn ? RainNow : 0.f) / StateRain, 0.f, 1.f) : 1.f;
	auto V = [&](const TCHAR* Key)
	{
		return FMath::Lerp(WeatherKey(Clear, Key), WeatherKey(S, Key), W);
	};
	const float OutWas = OutNow;
	OutNow = V(TEXT("out"));
	PaceNow = V(TEXT("pace"));
	RainLooksNow = V(TEXT("rain_looks"));
	UmbrellaNow = V(TEXT("umbrella"));
	ShelterNow = V(TEXT("shelter"));
	CarsNow = V(TEXT("cars"));
	SpeedNow = V(TEXT("speed"));
	HeadwayNow = V(TEXT("headway_s"));
	Frame.PaceMul = PaceNow;
	Frame.ShelterP = ShelterNow;
	Frame.SpeedMul = SpeedNow;
	Frame.HeadwayAdd = HeadwayNow;
	if (FMath::Abs(OutWas - OutNow) > 0.02f && bBuilt && IsCity())
	{
		// (the live walkways' numbers at once; the people out go in over their trips: ThinOut)
		UpdateLive(0.f, false);
	}
}

void ACityGenLife::FollowAtmos(const float Dt, const bool bNow)
{
	TRACE_CPUPROFILER_EVENT_SCOPE(CityGenLife_FollowAtmos);
	AtmosClock += Dt;
	if (!bNow && AtmosClock < AtmosStep)
	{
		return;
	}
	AtmosClock = 0.f;
	AActor* A = AtmosActor.Get();
	if (!A && !bAtmosLooked)
	{
		bAtmosLooked = true;
		for (TActorIterator<AActor> It(GetWorld()); It; ++It)
		{
			if (It->GetClass()->GetName() == TEXT("CityGenAtmos"))
			{
				A = *It;
				AtmosActor = A;
				break;
			}
		}
	}
	if (A && bFollowAtmos)
	{
		// the hour
		if (const FFloatProperty* P = FindFProperty<FFloatProperty>(A->GetClass(), TEXT("Hour")))
		{
			const float H = P->GetPropertyValue_InContainer(A);
			AtmosHour = H;
			const int32 Hn = ((FMath::FloorToInt(H) % 24) + 24) % 24;
			if (Hn != Hour && bBuilt)
			{
				const int32 D = FMath::Abs(Hn - Hour);
				const int32 Step = FMath::Min(D, 24 - D);
				if (Step == 1 && !bNow)
				{
					// (time running: an hour on; the doors' rates and the live numbers move, people
					// come out and go in over their trips)
					Hour = Hn;
					if (IsPlaces())
					{
						ApplyHour();
					}
					if (IsCity())
					{
						UpdateLive(0.f, false);
					}
					if (IsTraffic() && bTraffic)
					{
						UpdateTraffic(0.f, false);
					}
					++HourSteps;
				}
				else
				{
					SetHour(Hn);
					++HourJumps;
				}
			}
		}
		// the weather: the state it turns to and its rain
		if (WeatherHeld.IsEmpty())
		{
			FString Label;
			if (UFunction* F = A->FindFunction(TEXT("GetWeatherLabel")))
			{
				struct { FString Ret; } Parms;
				A->ProcessEvent(F, &Parms);
				Label = Parms.Ret;
			}
			FString To = Label;
			int32 Gt = INDEX_NONE;
			if (Label.FindChar(TEXT('>'), Gt))
			{
				To = Label.Mid(Gt + 1);
			}
			To.TrimStartAndEndInline();
			if (!To.IsEmpty() && WeatherNames.Contains(To))
			{
				WeatherState = To;
			}
			const FBoolProperty* PRain = FindFProperty<FBoolProperty>(A->GetClass(), TEXT("bRain"));
			const FFloatProperty* PRate = FindFProperty<FFloatProperty>(A->GetClass(), TEXT("RainRate"));
			const bool bRaining = PRain ? PRain->GetPropertyValue_InContainer(A) : false;
			RainNow = (bRaining && PRate) ? PRate->GetPropertyValue_InContainer(A) : 0.f;
		}
	}
	if (!WeatherHeld.IsEmpty())
	{
		WeatherState = WeatherHeld;
		const int32 S = WeatherNames.IndexOfByKey(WeatherHeld);
		RainNow = WeatherRain.IsValidIndex(S) ? WeatherRain[S] : 0.f;
	}
	ApplyWeatherNow();
}

void ACityGenLife::ThinOut()
{
	TRACE_CPUPROFILER_EVENT_SCOPE(CityGenLife_ThinOut);
	// (more people out than the hour and the weather want, by a tenth: some of those walking
	// head in at the next door ahead, as at a trip's end; never in sight of a door's absence:
	// one who meets none goes where nobody sees, as LG3's)
	if (!IsCity() || Entities.Num() == 0)
	{
		return;
	}
	const float Target = FMath::Min(WantLive, 0.92f * (float)(IsPlaces() ? CrowdPoolN : People));
	const int32 Over = ActiveNow - FMath::CeilToInt(1.1f * Target);
	if (Over <= 0)
	{
		return;
	}
	FMassEntityManager& EM = GetWorld()->GetSubsystem<UMassEntitySubsystem>()->GetMutableEntityManager();
	int32 Sent = 0;
	const int32 Want = FMath::Min(Over, 60);
	const int32 N = FMath::Min(People, Entities.Num());
	const int32 Start = N ? (int32)(CrowdRng.GetUnsignedInt() % (uint32)N) : 0;
	for (int32 I = 0; I < N && Sent < Want; ++I)
	{
		const int32 Slot = (Start + I) % N;
		FCgLifeWalker& W = EM.GetFragmentDataChecked<FCgLifeWalker>(Entities[Slot]);
		if (!W.Active || W.Role != CgRole::Crowd || W.State != CgWalk::Walk || W.TripLeft < 25.f || W.Flee || W.Gawk)
		{
			continue;
		}
		W.TripLeft = 5.f + 20.f * CrowdRng.FRand();
		++Sent;
	}
	Thinned += Sent;
}

bool ACityGenLife::HasUmbrella(const int32 P) const
{
	if (UmbrellaNow <= 0.f || !PersonSeed.IsValidIndex(P))
	{
		return false;
	}
	// (the rain looks have their hoods: no umbrella; of the others, the weather's share)
	if (RainGroup >= 0 && PersonGroup.IsValidIndex(P) && PersonGroup[P] == RainGroup)
	{
		return false;
	}
	if (PersonRole.IsValidIndex(P) && PersonRole[P] != CgRole::Crowd)
	{
		return false;
	}
	const float U = (float)(MixW((uint32)PersonSeed[P] ^ 0x9e3779b9u) % 10000u) / 10000.f;
	return U < UmbrellaNow;
}

bool ACityGenLife::UmbOpen(const int32 P) const
{
	return UmbCanopy && WalkState.IsValidIndex(P) && (WalkState[P] == CgShow::Moving || WalkState[P] == CgShow::Still) &&
		WalkPos.IsValidIndex(P) && !WalkPos[P].IsZero() &&
		!(WalkCovered.IsValidIndex(P) && WalkCovered[P]) &&
		!(WalkAnimG.IsValidIndex(P) && (CgAnim::IsSit(WalkAnimG[P]) || WalkAnimG[P] == CgAnim::Run)) &&
		HasUmbrella(P);
}

void ACityGenLife::MakeUmbHold()
{
	// (umbrella_hold: per clip group its held arm, from its clip's first key: the upper arm's,
	// forearm's and hand's rotations in their parents' frames, by the skeleton's indices)
	bUmbHoldMade = true;
	static const TCHAR* Names[] = {TEXT("upperarm_r"), TEXT("lowerarm_r"), TEXT("hand_r")};
	UmbHoldBones.SetNum(UmbHoldClips.Num());
	UmbHoldRots.SetNum(UmbHoldClips.Num());
	int32 Made = 0;
	for (int32 G = 0; G < UmbHoldClips.Num(); ++G)
	{
		UmbHoldBones[G].Reset();
		UmbHoldRots[G].Reset();
		const UAnimSequence* Clip = UmbHoldClips[G].Get();
		const USkeleton* Sk = Clip ? Clip->GetSkeleton() : nullptr;
		if (!Sk)
		{
			continue;
		}
		for (const TCHAR* Name : Names)
		{
			const int32 Bone = Sk->GetReferenceSkeleton().FindBoneIndex(FName(Name));
			if (Bone == INDEX_NONE)
			{
				UmbHoldBones[G].Reset();
				UmbHoldRots[G].Reset();
				break;
			}
			FTransform T;
			Clip->GetBoneTransform(T, FSkeletonPoseBoneIndex(Bone), FAnimExtractContext(0.0), false);
			UmbHoldBones[G].Add(Bone);
			UmbHoldRots[G].Add(T.GetRotation().GetNormalized());
		}
		Made += UmbHoldBones[G].Num() ? 1 : 0;
	}
	UE_LOG(LogTemp, Display, TEXT("CityGenLife: the umbrella's held arm for %d of %d clip groups"), Made, UmbHoldClips.Num());
}

void ACityGenLife::MakeUmbrellas()
{
	if (!UmbrellaCanopy || !UmbrellaShaft || !IsCity() || Umbrella.Num() < 8)
	{
		return;
	}
	auto Make = [this](const TCHAR* Name, UStaticMesh* Mesh)
	{
		UCgLifeISM* C = NewObject<UCgLifeISM>(this, Name);
		C->SetMobility(EComponentMobility::Movable);
		C->SetupAttachment(RootComponent);
		C->SetStaticMesh(Mesh);
		if (UmbrellaMaterial)
		{
			C->SetMaterial(0, UmbrellaMaterial);
		}
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetCanEverAffectNavigation(false);
		// (no shadow: as the mid people's, the umbrellas' would double their draws for a shadow
		// lost in the street's)
		C->SetCastShadow(false);
		C->bAffectDistanceFieldLighting = false;
		C->SetAffectDynamicIndirectLighting(false);
		C->NumCustomDataFloats = 6;
		C->SetCullDistances(0, (int32)(100.f * (MidM + 20.f)));
		C->RegisterComponent();
		FixBounds(C);
		return C;
	};
	UmbCanopy = Make(TEXT("Umbrellas"), UmbrellaCanopy);
	UmbShaft = Make(TEXT("UmbrellaShafts"), UmbrellaShaft);
	const int32 NP = FMath::Max(People, PersonChar.Num());
	UmbCanXf.Init(HiddenXf, NP);
	UmbShaftXf.Init(HiddenXf, NP);
	UmbShown.Init(0, NP);
	UmbCanopy->AddInstances(UmbCanXf, false, true, false);
	UmbShaft->AddInstances(UmbShaftXf, false, true, false);
	// (each person's umbrella: a canopy color of its hash; a lit shaft by the share, else dark)
	const int32 NC = UmbrellaColors.Num() / 3;
	const int32 NL = UmbrellaLit.Num() / 3;
	for (int32 P = 0; P < NP; ++P)
	{
		const uint32 H = MixW((uint32)(PersonSeed.IsValidIndex(P) ? PersonSeed[P] : P) + 0x51u);
		float Can[6] = {0.05f, 0.05f, 0.06f, 0.f, 0.f, 0.f};
		if (NC > 0)
		{
			const int32 C = (int32)(H % (uint32)NC);
			Can[0] = UmbrellaColors[3 * C];
			Can[1] = UmbrellaColors[3 * C + 1];
			Can[2] = UmbrellaColors[3 * C + 2];
		}
		float Sh[6] = {0.04f, 0.04f, 0.045f, 0.f, 0.f, 0.f};
		const bool bLit = (float)((H >> 8) % 1000u) / 1000.f < Umbrella[0] && NL > 0;
		if (bLit)
		{
			const int32 L = (int32)((H >> 4) % (uint32)NL);
			for (int32 Q = 0; Q < 3; ++Q)
			{
				Sh[Q] = 0.2f * UmbrellaLit[3 * L + Q];
				Sh[3 + Q] = 6.f * UmbrellaLit[3 * L + Q];
				// (a lit umbrella's canopy glows a little in its shaft's color)
				Can[3 + Q] = 0.06f * UmbrellaLit[3 * L + Q];
			}
		}
		UmbCanopy->SetCustomData(P, MakeArrayView(Can, 6), false);
		UmbShaft->SetCustomData(P, MakeArrayView(Sh, 6), false);
	}
	UmbCanopy->MarkRenderStateDirty();
	UmbShaft->MarkRenderStateDirty();
}

void ACityGenLife::UpdateUmbrellas(const FVector& View)
{
	TRACE_CPUPROFILER_EVENT_SCOPE(CityGenLife_UpdateUmbrellas);
	if (!UmbCanopy || !UmbShaft || UmbCanXf.Num() == 0)
	{
		return;
	}
	const int32 NP = FMath::Min(UmbCanXf.Num(), WalkPos.Num());
	const float CanW = Umbrella[1], CanH = Umbrella[2], Height = Umbrella[3], SideM = Umbrella[4], FwdM = Umbrella[5];
	const float Tilt = Umbrella[6], ShaftM = Umbrella[7];
	if (!bUmbHoldMade)
	{
		MakeUmbHold();
	}
	// (umbrella_hold: held in the hand where the library has the held arm; LG8's over the
	// shoulder otherwise)
	const bool bHeld = UmbGrip.Num() >= 3;
	const int32 NG = UmbGrip.Num() / 3;
	int32 On = 0, Folded = 0;
	bool bAny = false;
	for (int32 P = 0; P < NP; ++P)
	{
		const uint8 TierP = PersonTier.IsValidIndex(P) ? PersonTier[P] : 255;
		const bool bOpen = TierP <= 1 && UmbOpen(P);
		// (umbrella_hold: a near person's umbrella in its hand, from the drawn body's bones: open
		// once the arm is mostly up; folded and hanging from the hand while the arm is down (under
		// a cover, or rising to open it))
		USkeletalMeshComponent* Lead = nullptr;
		const UCgPersonAnim* Body = nullptr;
		if (bHeld && TierP == 0 && PersonSlot.IsValidIndex(P) && NearSlots.IsValidIndex(PersonSlot[P]) && NearSlots[PersonSlot[P]].Comps.Num())
		{
			Lead = NearSlots[PersonSlot[P]].Comps[0];
			Body = Lead ? Cast<UCgPersonAnim>(Lead->GetAnimInstance()) : nullptr;
		}
		const float HoldW = Body ? Body->HoldW : (bOpen ? 1.f : 0.f);
		const bool bHand = Lead && Body && Body->HoldBones.Num();
		const bool bShowOpen = bOpen && (!bHand || HoldW >= 0.6f);
		const bool bShowFurled = !bShowOpen && bHand && WalkState.IsValidIndex(P) && (WalkState[P] == CgShow::Moving || WalkState[P] == CgShow::Still) &&
			!(WalkAnimG.IsValidIndex(P) && (CgAnim::IsSit(WalkAnimG[P]) || WalkAnimG[P] == CgAnim::Run)) && HasUmbrella(P);
		if (!bShowOpen && !bShowFurled)
		{
			if (UmbShown[P])
			{
				UmbCanXf[P] = HiddenXf;
				UmbShaftXf[P] = HiddenXf;
				UmbShown[P] = 0;
				bAny = true;
			}
			continue;
		}
		const float Scale = PersonScale.IsValidIndex(P) ? PersonScale[P] : 1.f;
		const FVector Fwd = FRotator(0.f, WalkYaw[P], 0.f).Vector();
		const FVector Right = FVector::CrossProduct(FVector::UpVector, Fwd);
		bAny = true;
		if (!bHeld)
		{
			// (LG8: the canopy's middle over the right shoulder, a person's height and a bit up;
			// the shaft down from it toward the hand)
			const FRotator R(-Tilt, WalkYaw[P], 0.f);
			const FVector Up = R.RotateVector(FVector::UpVector);
			const FVector Mid = WalkPos[P] + Fwd * (100.f * FwdM) + Right * (100.f * SideM) +
				FVector(0.0, 0.0, 100.f * (1.75f * Scale * Height + 0.5f * CanH));
			UmbCanXf[P] = FTransform(R, Mid, FVector(CanW, CanW, CanH));
			UmbShaftXf[P] = FTransform(R, Mid - Up * (50.f * ShaftM), FVector(0.022f, 0.022f, ShaftM));
			UmbShown[P] = 1;
			++On;
			continue;
		}
		// the grip: near, the drawn hand (its wrist on along its forearm by the grip's share of the
		// arm, as the bake's); mid, the bake's grip in the body's frame
		FVector Grip;
		if (bHand)
		{
			const FVector Hand = Lead->GetSocketLocation(TEXT("hand_r"));
			const FVector Elbow = Lead->GetSocketLocation(TEXT("lowerarm_r"));
			const FVector Along = (Hand - Elbow).GetSafeNormal();
			Grip = Hand + Along * (0.3f * FVector::Dist(Hand, Elbow));
		}
		else
		{
			const int32 NC = FMath::Max(1, MidMeshes.Num());
			const int32 C = PersonChar.IsValidIndex(P) ? FMath::Clamp(PersonChar[P], 0, NC - 1) : 0;
			const int32 G = CharClipGroup.IsValidIndex(C) ? FMath::Clamp(CharClipGroup[C], 0, NG - 1) : 0;
			const FVector Local(UmbGrip[3 * G], UmbGrip[3 * G + 1], UmbGrip[3 * G + 2]);
			Grip = WalkPos[P] + FRotator(0.f, WalkYaw[P] + MeshYaw, 0.f).RotateVector(Local * Scale);
		}
		if (bShowFurled)
		{
			// (folded: the canopy furled into a thin cone, tip down, the shaft hanging from the
			// hand)
			const FQuat Down(FVector::ForwardVector, PI);
			UmbCanXf[P] = FTransform(Down, Grip - FVector(0.0, 0.0, 38.0 * Scale), FVector(0.085f, 0.085f, 0.5f * Scale));
			UmbShaftXf[P] = FTransform(FQuat::Identity, Grip - FVector(0.0, 0.0, 31.0 * Scale), FVector(0.02f, 0.02f, 0.72f * Scale));
			UmbShown[P] = 2;
			++Folded;
			continue;
		}
		// (open: the shaft up from the grip, leaning back toward the head by the tilt, the canopy
		// on its top no lower than LG8's over the head)
		const float T = FMath::DegreesToRadians(Tilt);
		const FVector Dir = (FVector::UpVector * FMath::Cos(T) - Fwd * FMath::Sin(T)).GetSafeNormal();
		const double TopZ = WalkPos[P].Z + 100.0 * (1.75 * Scale * Height + 0.5 * CanH);
		const double Len = FMath::Max(100.0 * ShaftM * Scale, (TopZ - Grip.Z) / FMath::Max(0.5, (double)Dir.Z));
		const FVector Mid = Grip + Dir * Len;
		const FQuat Q = FQuat::FindBetweenNormals(FVector::UpVector, Dir);
		UmbCanXf[P] = FTransform(Q, Mid, FVector(CanW, CanW, CanH));
		// (the shaft through the hand and 6 cm past it below: the handle)
		UmbShaftXf[P] = FTransform(Q, Grip + Dir * (0.5 * (Len - 6.0)), FVector(0.022f, 0.022f, (Len + 6.0) / 100.0));
		UmbShown[P] = 1;
		++On;
	}
	UmbrellasNow = On;
	UmbFoldedNow = Folded;
	if (bAny || bUmbSeen)
	{
		UmbCanopy->BatchUpdateInstancesTransforms(0, UmbCanXf, false, bRebuildRenderState, false);
		UmbShaft->BatchUpdateInstancesTransforms(0, UmbShaftXf, false, bRebuildRenderState, false);
	}
	bUmbSeen = On > 0;
	(void)View;
}

void ACityGenLife::SetFollowAtmos(bool bOn)
{
	bFollowAtmos = bOn;
	if (bOn && bBuilt)
	{
		FollowAtmos(0.f, true);
	}
}

bool ACityGenLife::SetWeather(const FString& State)
{
	if (State.Equals(TEXT("off"), ESearchCase::IgnoreCase))
	{
		bWeatherOn = false;
		WeatherHeld.Reset();
	}
	else if (State.Equals(TEXT("on"), ESearchCase::IgnoreCase) || State.Equals(TEXT("auto"), ESearchCase::IgnoreCase))
	{
		bWeatherOn = true;
		WeatherHeld.Reset();
	}
	else if (WeatherNames.Contains(State))
	{
		bWeatherOn = true;
		WeatherHeld = State;
	}
	else
	{
		return false;
	}
	FollowAtmos(0.f, true);
	return true;
}

void ACityGenLife::Panic(FVector Where, float InRadiusM, float InSeconds)
{
	if (!bBuilt || !IsCity() || !bFlee)
	{
		return;
	}
	const double Now = GetWorld()->GetTimeSeconds();
	++PanicCount;
	LastPanicAt = Where;
	Frame.PanicId = PanicCount;
	Frame.PanicAt = Where;
	Frame.PanicCm = 100.f * (InRadiusM > 0.f ? InRadiusM : FleeM);
	Frame.PanicUntil = Now + (InSeconds > 0.f ? InSeconds : FleeS);
	Frame.GatherUntil = Frame.PanicUntil + (bGather ? GatherS : 0.f);
	Frame.bGather = bGather;
	const FVector P = Where / 100.0;
	UE_LOG(LogTemp, Display, TEXT("CITYGEN_LIFE_PANIC {\"n\":%d,\"at\":[%.1f,%.1f,%.1f],\"radius_m\":%.1f,\"flee_s\":%.1f,\"gather_s\":%.1f}"),
		PanicCount, P.X, -P.Y, P.Z, Frame.PanicCm / 100.f, (float)(Frame.PanicUntil - Now), (float)(Frame.GatherUntil - Frame.PanicUntil));
}

bool ACityGenLife::PanicAtPlayer(float InRadiusM, float InSeconds)
{
	APlayerController* PC = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
	const APawn* Pawn = PC ? PC->GetPawn() : nullptr;
	FVector At;
	if (Pawn)
	{
		At = Pawn->GetActorLocation() - FVector(0.0, 0.0, 90.0);
	}
	else if (!ViewPoint(At))
	{
		return false;
	}
	Panic(At, InRadiusM, InSeconds);
	return true;
}

bool ACityGenLife::ShowWeather(const FString& What)
{
	if (!bBuilt || !IsCity())
	{
		return false;
	}
	FVector View;
	if (!ViewPoint(View))
	{
		View = LastLiveView;
	}
	int32 Best = INDEX_NONE;
	double BestD = 1.0e18;
	const int32 NP = WalkPos.Num();
	for (int32 P = 0; P < NP; ++P)
	{
		const bool bOn = WalkState.IsValidIndex(P) && (WalkState[P] == CgShow::Moving || WalkState[P] == CgShow::Still) && !WalkPos[P].IsZero();
		if (!bOn)
		{
			continue;
		}
		const uint8 Anim = WalkAnimG.IsValidIndex(P) ? WalkAnimG[P] : 0;
		bool bWant = false;
		if (What == TEXT("umbrella"))
		{
			bWant = UmbShown.IsValidIndex(P) && UmbShown[P] == 1 && WalkState[P] == CgShow::Moving;
		}
		else if (What == TEXT("umbrella_still"))
		{
			// (umbrella_hold: someone standing with its umbrella open)
			bWant = UmbShown.IsValidIndex(P) && UmbShown[P] == 1 && WalkState[P] == CgShow::Still && !CgAnim::IsSit(Anim);
		}
		else if (What == TEXT("umbrella_folded"))
		{
			// (umbrella_hold: someone near holding its umbrella folded, under a cover)
			bWant = UmbShown.IsValidIndex(P) && UmbShown[P] == 2;
		}
		else if (What == TEXT("shelter"))
		{
			bWant = WalkState[P] == CgShow::Still && Anim == CgAnim::Idle && WalkCovered.IsValidIndex(P) && WalkCovered[P];
		}
		else if (What == TEXT("look"))
		{
			bWant = WalkState[P] == CgShow::Still && !CgAnim::IsSit(Anim);
		}
		else if (What == TEXT("flee"))
		{
			bWant = Anim == CgAnim::Run;
		}
		else if (What == TEXT("gather"))
		{
			bWant = Anim == CgAnim::Idle && FVector::Dist2D(WalkPos[P], LastPanicAt) < 100.0 * GatherM;
		}
		else
		{
			bWant = WalkState[P] == CgShow::Moving;
		}
		const double D = FVector::Dist(WalkPos[P], View);
		if (bWant && D < BestD && D < 100.0 * LiveM)
		{
			BestD = D;
			Best = P;
		}
	}
	if (Best == INDEX_NONE)
	{
		LastWeatherShow = What + TEXT(":none");
		UE_LOG(LogTemp, Display, TEXT("CITYGEN_LIFE_SHOW {\"what\":\"%s\",\"found\":false}"), *What);
		return false;
	}
	const FVector At = WalkPos[Best];
	const FVector Fwd = FRotator(0.f, WalkYaw[Best], 0.f).Vector();
	bool bOk;
	if (What == TEXT("look"))
	{
		// (the camera, the player, 4 m in front of someone waiting at eye height: those near
		// turn to it)
		bOk = FrameCar(At, -Fwd, 400.0, 170.0, 0.0);
	}
	else if (What == TEXT("gather") || What == TEXT("flee"))
	{
		// (from over the danger's spot, back and up, the ring or the runners in view)
		const FVector Dir = (At - LastPanicAt).GetSafeNormal2D();
		bOk = FrameCar(LastPanicAt, Dir.IsNearlyZero() ? Fwd : Dir, 1400.0, 650.0, 300.0);
	}
	else
	{
		// (from ahead and to the side, a few meters off, at eye height)
		bOk = FrameCar(At, -Fwd, 650.0, 120.0, 200.0);
	}
	const FVector P = At / 100.0;
	LastWeatherShow = FString::Printf(TEXT("%s:%d"), *What, Best);
	UE_LOG(LogTemp, Display, TEXT("CITYGEN_LIFE_SHOW {\"what\":\"%s\",\"found\":true,\"person\":%d,\"at\":[%.1f,%.1f,%.1f]}"),
		*What, Best, P.X, -P.Y, P.Z);
	return bOk;
}

FString ACityGenLife::WeatherStatus() const
{
	if (!IsWeather())
	{
		return TEXT(",\"weather\":null");
	}
	return FString::Printf(TEXT(",\"weather\":{\"follow\":%s,\"atmos\":%s,\"atmos_hour\":%.2f,\"hour\":%d,\"hour_steps\":%d,\"hour_jumps\":%d,\"on\":%s,\"state\":\"%s\",\"held\":\"%s\",\"rain\":%.3f,\"out\":%.3f,\"pace\":%.3f,\"rain_looks\":%.3f,\"umbrella\":%.3f,\"shelter\":%.3f,\"cars\":%.3f,\"speed\":%.3f,\"headway_s\":%.2f,\"umbrellas\":%d,\"sheltering\":%d,\"looking\":%d,\"fleeing\":%d,\"gawking\":%d,\"panics\":%d,\"thinned\":%d,\"covered_stretches\":%d,\"show\":\"%s\"}"),
		bFollowAtmos ? TEXT("true") : TEXT("false"), AtmosActor.IsValid() ? TEXT("true") : TEXT("false"), AtmosHour, Hour, HourSteps, HourJumps,
		bWeatherOn ? TEXT("true") : TEXT("false"), *WeatherState, *WeatherHeld, RainNow, OutNow, PaceNow, RainLooksNow, UmbrellaNow, ShelterNow,
		CarsNow, SpeedNow, HeadwayNow, UmbrellasNow, Frame.Sheltering, Frame.Looking, Frame.Fleeing, Frame.Gawking, PanicCount, Thinned,
		CoverCm.Num() / 2, *LastWeatherShow)
		.LeftChop(1) + FString::Printf(TEXT(",\"umbrellas_folded\":%d,\"umbrella_held\":%s,\"umbrella_mid_held\":%s,\"umbrella_hold_groups\":%d}"),
			UmbFoldedNow, UmbGrip.Num() >= 3 ? TEXT("true") : TEXT("false"), HasMidUmb() ? TEXT("true") : TEXT("false"),
			UmbHoldBones.FilterByPredicate([](const TArray<int32>& B) { return B.Num() > 0; }).Num());
}
