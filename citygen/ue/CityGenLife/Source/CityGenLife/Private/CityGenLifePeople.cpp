// lifegen's people (LG1): the library's characters drawn by distance from the view. See
// CityGenLifeActor.h ("LG1: the people library") and docs/unreal_export.md ("From LG1").
//
// Every person is a Mass entity walking its walkway lane (LG0's walk processor writes WalkPos
// and WalkYaw); this file only draws them:
// - near (within NearM, the NearMax nearest): a pooled slot of skeletal mesh components (the
//   character's body leading its face, outfit and hair) playing the person's gait's clip in
//   single node mode at the person's pace, its post-process Blueprints (the face rig) off;
// - mid (within MidM): an instance of its character's mid mesh, the walk baked into bone
//   textures (AnimToTexture), playing on its own from per-instance custom data (time offset,
//   play rate, first and last frame), so the game thread only moves it;
// - far (within FarM): an instance of the impostor card in its character's sheet, which the
//   material turns to the view and steps through the walk (time offset, cycles a second).
// A person's walk keeps its phase from tier to tier (one time offset, one rate).
// The clothing switch (bClothing, lifegen_clothing_toggle), off: near, out to MidM, MetaHuman's
// whole body in place of each person's body and outfit; mid, the garment slots hidden; far as it
// was (ApplyClothing says why).

#include "CityGenLifeActor.h"
#include "CityGenLifeAnim.h"
#include "ProfilingDebugging/CpuProfilerTrace.h"
#include "CityGenLifeISM.h"
#include "CityGenLifeTypes.h"
#include "Algo/Sort.h"
#include "AnimationRuntime.h"
#include "Animation/AnimSequence.h"
#include "Animation/AnimationAsset.h"
#include "Animation/Skeleton.h"
#include "BoneIndices.h"
#include "Components/StaticMeshComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "HAL/PlatformTime.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"

namespace
{
	// LG2: the person's three dye colors (rgb each) and wear after the walk's floats
	constexpr int32 MidFloats = 14;    // time offset, play rate, first frame, last frame, 3 x rgb, wear
	constexpr int32 FarFloats = 14;    // time offset, cycles a second, 3 x rgb, wear; people_idles: first cell, cells
	const FTransform Hidden(FQuat::Identity, FVector(0.0, 0.0, -1.0e6), FVector(0.0));

	uint32 Mix(uint32 X)
	{
		X ^= X >> 16; X *= 0x7feb352du; X ^= X >> 15; X *= 0x846ca68bu; X ^= X >> 16;
		return X;
	}

	// people_surfaces: a near body's animation, the crossfading instance (CityGenLifeAnim.h)
	// in place of LG1's single node
	UCgPersonAnim* PersonAnimOf(USkeletalMeshComponent* Lead)
	{
		if (!Lead)
		{
			return nullptr;
		}
		if (Lead->GetAnimationMode() != EAnimationMode::AnimationBlueprint || Lead->GetAnimClass() != UCgPersonAnim::StaticClass())
		{
			Lead->SetAnimationMode(EAnimationMode::AnimationBlueprint);
			Lead->SetAnimInstanceClass(UCgPersonAnim::StaticClass());
		}
		return Cast<UCgPersonAnim>(Lead->GetAnimInstance());
	}

	// lifegen_clothing_toggle: the mid mesh's garment slots: the instances the library set to
	// take the person's own tint (`UseInstanceTint` 1, people_library.mid_mesh), or a slot named
	// after a material of the character's outfit (the mid mesh's slots keep their source
	// materials' names: `MI_WI_DefaultGarment_...`, `bodytype2_short`)
	bool IsMidGarment(const FStaticMaterial& S, const TSet<FString>& Outfit)
	{
		const UMaterialInterface* M = S.MaterialInterface;
		float Use = 0.f;
		if (M && M->GetScalarParameterValue(FHashedMaterialParameterInfo(TEXT("UseInstanceTint")), Use) && Use > 0.5f)
		{
			return true;
		}
		const FString Slot = S.MaterialSlotName.ToString();
		return Outfit.Contains(Slot) || Slot.Contains(TEXT("Garment"));
	}
}

void ACityGenLife::SetClothing(bool bOn)
{
	bClothing = bOn;
	ApplyClothing();
}

void ACityGenLife::ApplyClothing()
{
	// The creator's assembled bodies (near) and the mid meshes baked from them have their
	// triangles under the garments taken out, so hiding the garments alone leaves holes.
	// Unclothed, a near person's body and outfit are hidden and MetaHuman's whole template
	// body (WholeBody) follows its pose in the character's skin material (SlotClothing), and
	// the near tier reaches out to MidM (UpdatePeople; at most NearMax people); mid, past that
	// cap, the garment slots are drawn with HiddenMaterial (the holes stay: no whole body is
	// baked); the far cards keep the clothes their sheets were captured in.
	if (!bClothing && !HiddenMaterial && !bHiddenWarned)
	{
		bHiddenWarned = true;
		UE_LOG(LogTemp, Warning, TEXT("CityGenLife: no HiddenMaterial (an import before lifegen_clothing_toggle): the clothing switch does nothing"));
	}
	const bool bOff = Unclothed();
	for (FNearSlot& Slot : NearSlots)
	{
		if (Slot.Person != INDEX_NONE)
		{
			SlotClothing(Slot);
		}
	}
	for (int32 K = 0; K < MidComps.Num(); ++K)
	{
		UInstancedStaticMeshComponent* C = MidComps[K];
		if (!C || !MidGarment.IsValidIndex(K))
		{
			continue;
		}
		for (const int32 M : MidGarment[K])
		{
			C->SetMaterial(M, bOff ? HiddenMaterial.Get() : MidSlotMaterial(K, M));
		}
	}
}

void ACityGenLife::SlotClothing(FNearSlot& Slot)
{
	const bool bOff = Unclothed() && WholeBody && Slot.Whole;
	for (int32 K = 0; K < Slot.Comps.Num(); ++K)
	{
		USkeletalMeshComponent* C = Slot.Comps[K];
		if (!C)
		{
			continue;
		}
		const bool bMesh = C->GetSkeletalMeshAsset() != nullptr;
		// (the face, with the hair on it, stays; the body leads the pose even when hidden)
		const bool bOn = bMesh && (!bOff || K == HairOn);
		C->SetVisibility(bOn);
		C->SetComponentTickEnabled(bMesh && (bOn || K == 0));
		if (K == 0)
		{
			C->VisibilityBasedAnimTickOption = bOff ? EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones
				: EVisibilityBasedAnimTickOption::OnlyTickPoseWhenRendered;
		}
	}
	if (Slot.Whole)
	{
		Slot.Whole->SetVisibility(bOff);
		Slot.Whole->SetComponentTickEnabled(bOff);
	}
}
void ACityGenLife::SetTiers(float InNearM, int32 InNearMax, float InMidM, float InFarM)
{
	NearM = FMath::Max(0.f, InNearM);
	NearMax = FMath::Max(0, InNearMax);
	MidM = FMath::Max(NearM, InMidM);
	FarM = FMath::Max(MidM, InFarM);
	// (slots past the new cap let go at once)
	for (int32 S = NearMax; S < NearSlots.Num(); ++S)
	{
		Release(S);
	}
}

float ACityGenLife::WalkRate(const int32 P) const
{
	// the clip's own speed against the person's pace: how fast the walk plays
	const int32 G = PersonGait.IsValidIndex(P) ? PersonGait[P] : 0;
	const float ClipV = WalkClipSpeeds.IsValidIndex(G) && WalkClipSpeeds[G] > 0.1f ? WalkClipSpeeds[G] : 1.3f;
	// (LG8: faster in the rain, by the weather's pace)
	const float Pace = (PersonPace.IsValidIndex(P) ? PersonPace[P] : 1.35f) * PaceNow;
	return FMath::Clamp(Pace / ClipV, 0.5f, 2.0f);
}

float ACityGenLife::PhaseOffset(const int32 P) const
{
	const uint32 S = PersonSeed.IsValidIndex(P) ? (uint32)PersonSeed[P] : Mix((uint32)P + 17u);
	return (Mix(S) % 10000u) / 1000.f;      // seconds, 0 to 10
}

namespace
{
	/** The frame (at `Fps` from the clip's start, within its first `N`) of a walk's passing
	 *  pose: where both thighs are nearest their mean turn over the loop (the legs together
	 *  under the body), a pose a person can stand in; -1 when the clip has no thighs. */
	float PassingFrame(const UAnimSequence* Clip, const float Fps, const int32 N)
	{
		const USkeleton* Sk = Clip ? Clip->GetSkeleton() : nullptr;
		if (!Sk || N < 2)
		{
			return -1.f;
		}
		const FReferenceSkeleton& Ref = Sk->GetReferenceSkeleton();
		const int32 Bones[2] = {Ref.FindBoneIndex(TEXT("thigh_l")), Ref.FindBoneIndex(TEXT("thigh_r"))};
		if (Bones[0] == INDEX_NONE || Bones[1] == INDEX_NONE)
		{
			return -1.f;
		}
		TArray<FQuat> Q[2];
		FQuat Mean[2];
		for (int32 B = 0; B < 2; ++B)
		{
			FVector4 Sum(0.0, 0.0, 0.0, 0.0);
			for (int32 K = 0; K < N; ++K)
			{
				FTransform T;
				Clip->GetBoneTransform(T, FSkeletonPoseBoneIndex(Bones[B]), FAnimExtractContext((double)K / Fps), false);
				FQuat R = T.GetRotation();
				if (Q[B].Num() && (Q[B][0] | R) < 0.0)
				{
					R = -R;
				}
				Q[B].Add(R);
				Sum += FVector4(R.X, R.Y, R.Z, R.W);
			}
			Mean[B] = FQuat(Sum.X, Sum.Y, Sum.Z, Sum.W).GetNormalized();
		}
		int32 Best = 0;
		double BestDev = 1.0e9;
		for (int32 K = 0; K < N; ++K)
		{
			const double Dev = Q[0][K].AngularDistance(Mean[0]) + Q[1][K].AngularDistance(Mean[1]);
			if (Dev < BestDev)
			{
				BestDev = Dev;
				Best = K;
			}
		}
		return (float)Best;
	}
}

void ACityGenLife::MakeMidLoops()
{
	// (lifegen_people_fixes) Per character its baked walk's loop and standing frame. The bake
	// sampled the clip's own frame count (its 30 fps keys) at the bake's 15 fps, so it ran
	// twice the clip's length and its second half held the clip's last pose: mid people walked
	// half the time and slid frozen the rest. The loop is the clip's length at the bake's
	// rate from its first frame (a library baked since lifegen_people_fixes bakes just that
	// loop). A person standing holds the walk's passing pose, not LG3's frozen first frame (mid
	// stride).
	const int32 NC = MidMeshes.Num();
	MidFirst.SetNum(NC);
	MidLast.SetNum(NC);
	MidStand.SetNum(NC);
	StandShare.SetNum(NC);
	TMap<const UAnimSequence*, float> Passing;
	for (int32 C = 0; C < NC; ++C)
	{
		const float Start = MidFrames.IsValidIndex(4 * C) ? MidFrames[4 * C] : 0.f;
		const float End = MidFrames.IsValidIndex(4 * C + 1) ? MidFrames[4 * C + 1] : Start;
		const float Fps = MidFrames.IsValidIndex(4 * C + 2) && MidFrames[4 * C + 2] > 1.f ? MidFrames[4 * C + 2] : 15.f;
		const float Cycle = MidFrames.IsValidIndex(4 * C + 3) && MidFrames[4 * C + 3] > 0.05f ? MidFrames[4 * C + 3] : 1.f;
		// (the bake's clip: the group's first walk)
		const int32 Group = CharClipGroup.IsValidIndex(C) ? CharClipGroup[C] : 0;
		const int32 G = FMath::Clamp(Group * FMath::Max(1, Gaits), 0, FMath::Max(0, WalkClips.Num() - 1));
		const UAnimSequence* Clip = WalkClips.IsValidIndex(G) ? WalkClips[G].Get() : nullptr;
		int32 N = FMath::Max(1, FMath::RoundToInt(End - Start) + 1);
		if (Clip)
		{
			N = FMath::Clamp(FMath::RoundToInt(Clip->GetPlayLength() * Fps), 2, N);
		}
		MidFirst[C] = Start;
		MidLast[C] = Start + (float)(N - 1);
		float K = -1.f;
		if (const float* Have = Passing.Find(Clip))
		{
			K = *Have;
		}
		else
		{
			K = PassingFrame(Clip, Fps, N);
			Passing.Add(Clip, K);
			UE_LOG(LogTemp, Display, TEXT("CityGenLife: the walk %s loops %d frames at %.0f fps, its passing pose at frame %.0f"),
				Clip ? *Clip->GetName() : TEXT("(none)"), N, Fps, K);
		}
		K = K >= 0.f ? K : 0.f;
		MidStand[C] = Start + K;
		// (the far card's cell nearest that pose: its sheet steps through one stride, Cycle s,
		// in CardFrames cells)
		const int32 F = FMath::Max(1, CardFrames);
		const float At = FMath::Fmod(K / Fps, Cycle) / Cycle;
		const int32 Cell = FMath::RoundToInt(At * F) % F;
		StandShare[C] = ((float)Cell + 0.5f) / (float)F;
	}
}

void ACityGenLife::TintOf(const int32 P, const int32 Ch, float Out[3]) const
{
	// (LG2: 9 floats a person, its three dye channels; before LG2 one color for all)
	const bool bNine = PersonTint.Num() >= 9 * FMath::Max(1, People) && PersonTint.IsValidIndex(9 * P + 8);
	for (int32 Q = 0; Q < 3; ++Q)
	{
		const int32 I = bNine ? 9 * P + 3 * Ch + Q : 3 * P + Q;
		Out[Q] = PersonTint.IsValidIndex(I) ? PersonTint[I] : 0.5f;
	}
}

UMaterialInterface* ACityGenLife::MidSlotMaterial(const int32 C, const int32 M) const
{
	if (!MidIdleStarts.IsValidIndex(C + 1))
	{
		return nullptr;
	}
	const int32 I = MidIdleStarts[C] + M;
	return I < MidIdleStarts[C + 1] && MidIdleMaterials.IsValidIndex(I) ? MidIdleMaterials[I].Get() : nullptr;
}

void ACityGenLife::LookData(const int32 P, const uint8 LookIn, float Mid[14], float Far[14]) const
{
	// (umbrella_hold: the flag CgLook::Umb, on a walk or a stand, plays the bake's loop with the
	// arm held; the far card as without)
	const uint8 Look = (uint8)(LookIn & ~(uint32)CgLook::Umb);
	// (the mid instance: time offset, rate, first and last frame of its loop, the tint; the far
	// card: time offset, strides a second, the tint, its first cell and cells. Standing, the
	// mid instance loops its one passing frame at the walk's rate; the card shows that pose's
	// cell: a stride rate so slow it does not move, its offset putting the cell's middle at
	// now. people_idles, with the idles' bakes: standing, the mid instance plays the baked
	// standing idle, sitting the bench's sitting loop, each from its own place in the loop; the
	// card holds one of the still sheet's sitting or standing cells, the person's own)
	const int32 NC = FMath::Max(1, MidMeshes.Num());
	const int32 C = PersonChar.IsValidIndex(P) ? FMath::Clamp(PersonChar[P], 0, NC - 1) : P % NC;
	const bool bStill = Look == CgLook::Still || Look == CgLook::Sit;
	const bool bIdles = HasMidIdles() && MidStillFrames.IsValidIndex(4 * C + 3);
	const bool bCells = CardCells.Num() >= 6;
	// (LG8: running from a danger, the baked walk played at the flight's pace)
	const bool bRun = Look == CgLook::Run;
	const float Rate = FMath::Max(0.05f, WalkRate(P) * (bRun ? FMath::Clamp(FleePace, 1.f, 3.f) : 1.f));
	const float T0 = PhaseOffset(P);
	const float Tint[3] = {
		PersonTint.IsValidIndex(3 * P) ? PersonTint[3 * P] : 0.5f,
		PersonTint.IsValidIndex(3 * P + 1) ? PersonTint[3 * P + 1] : 0.5f,
		PersonTint.IsValidIndex(3 * P + 2) ? PersonTint[3 * P + 2] : 0.5f};
	const float First = MidFirst.IsValidIndex(C) ? MidFirst[C] : (MidFrames.IsValidIndex(4 * C) ? MidFrames[4 * C] : 0.f);
	const float Last = MidLast.IsValidIndex(C) ? MidLast[C] : (MidFrames.IsValidIndex(4 * C + 1) ? MidFrames[4 * C + 1] : First);
	const float Stand = MidStand.IsValidIndex(C) ? MidStand[C] : First;
	Mid[0] = T0;
	Mid[1] = Rate;
	Mid[2] = bStill ? Stand : First;
	Mid[3] = bStill ? Stand : Last;
	if (bStill && bIdles)
	{
		// (a person's own pace through the loop: 0.85 to 1.15 of the clip's)
		const uint32 S = Mix((uint32)(PersonSeed.IsValidIndex(P) ? PersonSeed[P] : P) + 101u);
		const int32 K = Look == CgLook::Sit ? 2 : 0;
		Mid[1] = 0.85f + 0.3f * (float)(S % 1000u) / 1000.f;
		Mid[2] = MidStillFrames[4 * C + K];
		Mid[3] = MidStillFrames[4 * C + K + 1];
	}
	if ((LookIn & CgLook::Umb) && HasMidUmb() && MidUmbFrames.IsValidIndex(4 * C + 3) && MidUmbFrames[4 * C + 3] > 0.5f)
	{
		if (Look == CgLook::Walk)
		{
			// (the walk with the arm held: the same loop, its frames on by the bake's offset)
			Mid[2] = First + MidUmbFrames[4 * C];
			Mid[3] = Last + MidUmbFrames[4 * C];
		}
		else if (Look == CgLook::Still && bIdles)
		{
			Mid[2] = MidUmbFrames[4 * C + 1];
			Mid[3] = MidUmbFrames[4 * C + 2];
		}
	}
	const float Cycle = MidFrames.IsValidIndex(4 * C + 3) && MidFrames[4 * C + 3] > 0.05f ? MidFrames[4 * C + 3] : 1.f;
	Far[12] = bCells ? CardCells[0] : 0.f;
	Far[13] = bCells ? CardCells[1] : 0.f;
	if (bStill && bCells)
	{
		// (a still cell of its own: the still sheet's sitting or standing poses)
		const uint32 S = Mix((uint32)(PersonSeed.IsValidIndex(P) ? PersonSeed[P] : P) + 7u);
		const int32 K = Look == CgLook::Sit ? 2 : 4;
		const int32 N = FMath::Max(1, FMath::RoundToInt(CardCells[K + 1]));
		Far[0] = 0.f;
		Far[1] = 0.f;
		Far[12] = CardCells[K] + (float)(S % (uint32)N);
		Far[13] = 1.f;
	}
	else if (bStill)
	{
		constexpr float Slow = 1.0e-5f;
		const float Now = GetWorld() ? (float)GetWorld()->GetTimeSeconds() : 0.f;
		Far[0] = (StandShare.IsValidIndex(C) ? StandShare[C] : 0.0625f) / Slow - Now;
		Far[1] = Slow;
	}
	else
	{
		Far[0] = T0;
		Far[1] = Rate / Cycle;
	}
	for (int32 Ch = 0; Ch < 3; ++Ch)
	{
		float T[3];
		TintOf(P, Ch, T);
		for (int32 K = 0; K < 3; ++K)
		{
			Mid[4 + 3 * Ch + K] = T[K];
			Far[2 + 3 * Ch + K] = T[K];
		}
	}
	const float Wear = PersonWear.IsValidIndex(P) ? PersonWear[P] : 0.f;
	Mid[13] = Wear;
	Far[11] = Wear;
	(void)Tint;
}

void ACityGenLife::MakePeople()
{
	const int32 NC = MidMeshes.Num();
	MakeMidLoops();
	MidComps.Reset();
	FarComps.Reset();
	auto Make = [this](const FString& Name, UStaticMesh* Mesh, UMaterialInterface* Mat, const int32 Floats, const bool bShadow, const float CullM)
	{
		UInstancedStaticMeshComponent* C = NewObject<UCgLifeISM>(this, *Name);
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
		C->bAffectDistanceFieldLighting = false;
		C->SetAffectDynamicIndirectLighting(false);
		C->NumCustomDataFloats = Floats;
		C->SetCullDistances(0, (int32)(CullM * 100.f));
		C->RegisterComponent();
		FixBounds(C);
		return C;
	};
	MidGarment.Reset();
	MidGarment.SetNum(NC);
	for (int32 K = 0; K < NC; ++K)
	{
		// (the mid tier casts no shadow: a mid mesh has a section per creator slot, and its
		// shadow depths doubled the people's draws for a shadow too small to see past NearM)
		MidComps.Add(MidMeshes[K] ? Make(FString::Printf(TEXT("PeopleMid%d"), K), MidMeshes[K], nullptr, MidFloats, false, MidM + 20.f) : nullptr);
		// (people_idles: its slots read the idles' bake, the library's walk first in it)
		if (UInstancedStaticMeshComponent* Mc = MidComps.Last().Get())
		{
			for (int32 M = 0; M < Mc->GetNumMaterials(); ++M)
			{
				if (UMaterialInterface* Mi = MidSlotMaterial(K, M))
				{
					Mc->SetMaterial(M, Mi);
				}
			}
		}
		UMaterialInterface* Card = CardMaterials.IsValidIndex(K) ? CardMaterials[K].Get() : nullptr;
		FarComps.Add(CardMesh ? Make(FString::Printf(TEXT("PeopleFar%d"), K), CardMesh, Card, FarFloats, false, FarM + 20.f) : nullptr);
		// (lifegen_clothing_toggle: which of its slots are garments: by the materials of its
		// near meshes past the body and the face, its outfit)
		TSet<FString> Outfit;
		const int32 A = NearMeshStarts.IsValidIndex(K) ? NearMeshStarts[K] : 0;
		const int32 B = NearMeshStarts.IsValidIndex(K + 1) ? NearMeshStarts[K + 1] : A;
		for (int32 I = A + 1; I < B; ++I)
		{
			const USkeletalMesh* Sk = NearMeshes.IsValidIndex(I) ? NearMeshes[I].Get() : nullptr;
			if (!Sk || I - A == HairOn)
			{
				continue;
			}
			for (const FSkeletalMaterial& Sm : Sk->GetMaterials())
			{
				if (Sm.MaterialInterface)
				{
					Outfit.Add(Sm.MaterialInterface->GetName());
				}
			}
		}
		if (const UStaticMesh* Mesh = MidMeshes[K].Get())
		{
			const TArray<FStaticMaterial>& Mats = Mesh->GetStaticMaterials();
			for (int32 M = 0; M < Mats.Num(); ++M)
			{
				if (IsMidGarment(Mats[M], Outfit))
				{
					MidGarment[K].Add(M);
				}
			}
		}
	}
	ApplyClothing();
}

void ACityGenLife::SpawnPeople(const int32 NP)
{
	const int32 NC = MidMeshes.Num();
	for (int32 S = 0; S < NearSlots.Num(); ++S)
	{
		Release(S);
	}
	PersonInst.SetNumZeroed(NP);
	PersonSlot.Init(INDEX_NONE, NP);
	PersonTier.Init(255, NP);
	CharCount.SetNumZeroed(NC);
	MidXf.SetNum(NC);
	FarXf.SetNum(NC);
	for (int32 P = 0; P < NP; ++P)
	{
		const int32 C = PersonChar.IsValidIndex(P) ? FMath::Clamp(PersonChar[P], 0, NC - 1) : P % NC;
		PersonInst[P] = CharCount[C]++;
	}
	// (each character's instances: one per person of it, hidden until drawn; their custom data
	// once, since a person's walk, pace and tint stay theirs)
	for (int32 K = 0; K < NC; ++K)
	{
		MidXf[K].Init(Hidden, CharCount[K]);
		FarXf[K].Init(Hidden, CharCount[K]);
		for (UInstancedStaticMeshComponent* Comp : {MidComps.IsValidIndex(K) ? MidComps[K].Get() : nullptr, FarComps.IsValidIndex(K) ? FarComps[K].Get() : nullptr})
		{
			if (Comp)
			{
				Comp->ClearInstances();
				Comp->AddInstances(MidXf[K], false, true, false);
			}
		}
	}
	for (int32 P = 0; P < NP; ++P)
	{
		const int32 C = PersonChar.IsValidIndex(P) ? FMath::Clamp(PersonChar[P], 0, NC - 1) : P % NC;
		float MidData[14], FarData[14];
		LookData(P, CgLook::Walk, MidData, FarData);
		if (UInstancedStaticMeshComponent* Mid = MidComps.IsValidIndex(C) ? MidComps[C].Get() : nullptr)
		{
			Mid->SetCustomData(PersonInst[P], MakeArrayView(MidData, MidFloats), false);
		}
		if (UInstancedStaticMeshComponent* Far = FarComps.IsValidIndex(C) ? FarComps[C].Get() : nullptr)
		{
			Far->SetCustomData(PersonInst[P], MakeArrayView(FarData, FarFloats), false);
		}
	}
	for (UInstancedStaticMeshComponent* Comp : MidComps)
	{
		if (Comp) { Comp->MarkRenderStateDirty(); }
	}
	for (UInstancedStaticMeshComponent* Comp : FarComps)
	{
		if (Comp) { Comp->MarkRenderStateDirty(); }
	}
}

void ACityGenLife::Release(const int32 S)
{
	if (!NearSlots.IsValidIndex(S))
	{
		return;
	}
	FNearSlot& Slot = NearSlots[S];
	if (PersonSlot.IsValidIndex(Slot.Person))
	{
		PersonSlot[Slot.Person] = INDEX_NONE;
	}
	Slot.Person = INDEX_NONE;
	for (USkeletalMeshComponent* C : Slot.Comps)
	{
		if (C)
		{
			C->SetVisibility(false);
			C->SetComponentTickEnabled(false);
		}
	}
	if (Slot.Hair)
	{
		Slot.Hair->SetVisibility(false);
	}
	if (Slot.Whole)
	{
		Slot.Whole->SetVisibility(false);
		Slot.Whole->SetComponentTickEnabled(false);
	}
}

void ACityGenLife::Assign(const int32 S, const int32 P)
{
	if (!NearSlots.IsValidIndex(S))
	{
		NearSlots.SetNum(S + 1);
	}
	FNearSlot& Slot = NearSlots[S];
	const int32 C = PersonChar.IsValidIndex(P) ? FMath::Clamp(PersonChar[P], 0, MidMeshes.Num() - 1) : 0;
	const int32 A = NearMeshStarts.IsValidIndex(C) ? NearMeshStarts[C] : 0;
	const int32 B = NearMeshStarts.IsValidIndex(C + 1) ? NearMeshStarts[C + 1] : A;
	// (the slot's components: as many as the character has meshes, the first leading)
	while (Slot.Comps.Num() < B - A)
	{
		USkeletalMeshComponent* Comp = NewObject<USkeletalMeshComponent>(this, *FString::Printf(TEXT("PeopleNear%d_%d"), S, Slot.Comps.Num()));
		Comp->SetMobility(EComponentMobility::Movable);
		if (Slot.Comps.Num() == 0)
		{
			Comp->SetupAttachment(RootComponent);
			// (people_surfaces: its pose after this actor's tick, so a clip asked for and the
			// mesh moved to a seat in the same frame show together)
			Comp->AddTickPrerequisiteActor(this);
		}
		else
		{
			Comp->SetupAttachment(Slot.Comps[0]);
		}
		Comp->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Comp->SetCanEverAffectNavigation(false);
		Comp->SetGenerateOverlapEvents(false);
		Comp->bAffectDistanceFieldLighting = false;
		Comp->SetAffectDynamicIndirectLighting(false);
		Comp->SetCastShadow(bShadows);
		// (the crowd's bodies: the pose ticks only while seen, at a lower rate further off; no
		// post-process Blueprints: the face rig and the body's correctives cost the most)
		Comp->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::OnlyTickPoseWhenRendered;
		Comp->bEnableUpdateRateOptimizations = true;
		Comp->SetDisablePostProcessBlueprint(true);
		Comp->bPropagateCurvesToFollowers = false;
		// (LG8's performance pass: the leader's bounds from its physics asset, fixed, the
		// followers' its own: no bounds measured over every mesh's bones every frame)
		Comp->bComponentUseFixedSkelBounds = Slot.Comps.Num() == 0;
		Comp->bUseBoundsFromLeaderPoseComponent = Slot.Comps.Num() > 0;
		Comp->RegisterComponent();
		NearComps.Add(Comp);
		Slot.Comps.Add(Comp);
	}
	USkeletalMeshComponent* Lead = Slot.Comps[0];
	if (Slot.Char != C)
	{
		for (int32 K = 0; K < Slot.Comps.Num(); ++K)
		{
			USkeletalMeshComponent* Comp = Slot.Comps[K];
			USkeletalMesh* Mesh = (A + K < B && NearMeshes.IsValidIndex(A + K)) ? NearMeshes[A + K].Get() : nullptr;
			Comp->EmptyOverrideMaterials();
			Comp->SetSkeletalMesh(Mesh, false);
			if (K > 0)
			{
				Comp->SetLeaderPoseComponent(Mesh ? Lead : nullptr);
			}
			// (the garments: a dynamic instance a slot, which takes each person's own colors and
			// wear; LG2's are instances of M_CgGarment under People/Materials/Garments. LG8: one
			// per slot and parent material, made once and kept: a slot taking another person
			// reuses it, so no material instance becomes garbage as people come and go near the
			// view (they had kept the garbage collector busy, 2 to 5 ms a frame on the walk))
			for (int32 M = 0; Mesh && M < Comp->GetNumMaterials(); ++M)
			{
				UMaterialInterface* Mat = Comp->GetMaterial(M);
				if (Mat && (Mat->GetName().Contains(TEXT("Garment")) || Mat->GetPathName().Contains(TEXT("/Garments/"))))
				{
					const uint64 Key = ((uint64)(uint32)S << 32) | (uint64)Mat->GetUniqueID();
					UMaterialInstanceDynamic* D = nullptr;
					if (const TObjectPtr<UMaterialInstanceDynamic>* Have = NearMIDOf.Find(Key))
					{
						D = Have->Get();
					}
					if (!D)
					{
						D = UMaterialInstanceDynamic::Create(Mat, this);
						NearMIDs.Add(D);
						NearMIDOf.Add(Key, D);
					}
					Comp->SetMaterial(M, D);
				}
			}
		}
		// (its hair: the groom's cards on the face's head bone, placed by the bone's reference
		// pose, since the cards are in the face's frame at that pose)
		UStaticMesh* HairMesh = NearHair.IsValidIndex(C) ? NearHair[C].Get() : nullptr;
		USkeletalMeshComponent* On = Slot.Comps.IsValidIndex(HairOn) ? Slot.Comps[HairOn] : Lead;
		if (HairMesh && !Slot.Hair)
		{
			Slot.Hair = NewObject<UStaticMeshComponent>(this, *FString::Printf(TEXT("PeopleHair%d"), S));
			Slot.Hair->SetMobility(EComponentMobility::Movable);
			Slot.Hair->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			Slot.Hair->SetCanEverAffectNavigation(false);
			Slot.Hair->bAffectDistanceFieldLighting = false;
			Slot.Hair->SetAffectDynamicIndirectLighting(false);
			Slot.Hair->SetCastShadow(bShadows);
			Slot.Hair->SetupAttachment(On);
			Slot.Hair->RegisterComponent();
			HairComps.Add(Slot.Hair);
		}
		if (Slot.Hair)
		{
			Slot.Hair->SetStaticMesh(HairMesh);
			FTransform Rel = FTransform::Identity;
			const USkeletalMesh* Face = On ? On->GetSkeletalMeshAsset() : nullptr;
			const int32 Bone = Face ? Face->GetRefSkeleton().FindBoneIndex(TEXT("head")) : INDEX_NONE;
			if (Bone != INDEX_NONE)
			{
				Rel = FAnimationRuntime::GetComponentSpaceTransformRefPose(Face->GetRefSkeleton(), Bone).Inverse();
				Slot.Hair->AttachToComponent(On, FAttachmentTransformRules::KeepRelativeTransform, TEXT("head"));
			}
			Slot.Hair->SetRelativeTransform(Rel);
		}
		Slot.Char = C;
		Slot.Gait = INDEX_NONE;
	}
	const int32 Group = CharClipGroup.IsValidIndex(C) ? CharClipGroup[C] : 0;
	const int32 Gait = PersonGait.IsValidIndex(P) ? FMath::Clamp(PersonGait[P], 0, FMath::Max(0, Gaits - 1)) : 0;
	const int32 G = FMath::Clamp(Group * FMath::Max(1, Gaits) + Gait, 0, FMath::Max(0, WalkClips.Num() - 1));
	UAnimSequence* Clip = WalkClips.IsValidIndex(G) ? WalkClips[G].Get() : nullptr;
	// (people_surfaces: the walk, at once: no blend from the slot's last person; its rate and
	// phase below)
	UCgPersonAnim* Anim = PersonAnimOf(Lead);
	if (Clip && Anim)
	{
		Anim->Play(Clip, true, 1.f, 0.f, 0.f);
		Slot.Gait = G;
	}
	Slot.Clip = 0;
	Slot.bFresh = true;
	// (umbrella_hold: its group's held arm, held at once if its umbrella is open as it comes near)
	if (Anim)
	{
		if (!bUmbHoldMade)
		{
			MakeUmbHold();
		}
		if (UmbHoldBones.IsValidIndex(Group) && UmbHoldBones[Group].Num())
		{
			Anim->SetHold(UmbHoldBones[Group], UmbHoldRots[Group]);
		}
		else
		{
			Anim->SetHold(TArray<int32>(), TArray<FQuat>());
		}
		Anim->HoldS = UmbHoldS;
		Anim->HoldTarget = Anim->HoldW = UmbOpen(P) ? 1.f : 0.f;
	}
	// (the person's outfit color: the plan's tint, on the garments' dye)
	const FLinearColor Tint(PersonTint.IsValidIndex(3 * P) ? PersonTint[3 * P] : 0.5f,
		PersonTint.IsValidIndex(3 * P + 1) ? PersonTint[3 * P + 1] : 0.5f,
		PersonTint.IsValidIndex(3 * P + 2) ? PersonTint[3 * P + 2] : 0.5f);
	float T3[3][3];
	for (int32 Ch = 0; Ch < 3; ++Ch)
	{
		TintOf(P, Ch, T3[Ch]);
	}
	const float Wear = PersonWear.IsValidIndex(P) ? PersonWear[P] : 0.f;
	for (USkeletalMeshComponent* Comp : Slot.Comps)
	{
		for (int32 M = 0; Comp && M < Comp->GetNumMaterials(); ++M)
		{
			if (UMaterialInstanceDynamic* D = Cast<UMaterialInstanceDynamic>(Comp->GetMaterial(M)))
			{
				D->SetVectorParameterValue(TEXT("diffuse_color_1"), Tint);
				for (int32 Ch = 0; Ch < 3; ++Ch)
				{
					D->SetVectorParameterValue(*FString::Printf(TEXT("Tint%d"), Ch), FLinearColor(T3[Ch][0], T3[Ch][1], T3[Ch][2]));
				}
				D->SetScalarParameterValue(TEXT("Wear"), Wear);
			}
		}
	}
	const float Rate = WalkRate(P);
	if (Anim)
	{
		Anim->SetRate(Rate);
	}
	if (Clip && Anim)
	{
		// (in phase with its baked walk: the same time offset and rate)
		const float Len = FMath::Max(0.1f, Clip->GetPlayLength());
		const float T = (float)GetWorld()->GetTimeSeconds() + PhaseOffset(P);
		Anim->SetTime(FMath::Fmod(T * Rate, Len));
	}
	// (lifegen_clothing_toggle: the whole body, made once a slot, in the character's skin)
	if (WholeBody && !Slot.Whole)
	{
		Slot.Whole = NewObject<USkeletalMeshComponent>(this, *FString::Printf(TEXT("PeopleWhole%d"), S));
		Slot.Whole->SetMobility(EComponentMobility::Movable);
		Slot.Whole->SetupAttachment(Lead);
		Slot.Whole->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Slot.Whole->SetCanEverAffectNavigation(false);
		Slot.Whole->SetGenerateOverlapEvents(false);
		Slot.Whole->bAffectDistanceFieldLighting = false;
		Slot.Whole->SetAffectDynamicIndirectLighting(false);
		Slot.Whole->SetCastShadow(bShadows);
		Slot.Whole->SetDisablePostProcessBlueprint(true);
		Slot.Whole->SetSkeletalMesh(WholeBody, false);
		Slot.Whole->SetLeaderPoseComponent(Lead);
		Slot.Whole->SetVisibility(false);
		Slot.Whole->RegisterComponent();
		WholeComps.Add(Slot.Whole);
	}
	if (Slot.Whole)
	{
		UMaterialInterface* Skin = Lead->GetSkeletalMeshAsset() ? Lead->GetMaterial(0) : nullptr;
		for (int32 M = 0; Skin && M < Slot.Whole->GetNumMaterials(); ++M)
		{
			Slot.Whole->SetMaterial(M, Skin);
		}
	}
	SlotClothing(Slot);
	if (Slot.Hair)
	{
		Slot.Hair->SetVisibility(Slot.Hair->GetStaticMesh() != nullptr);
	}
	Slot.Person = P;
	PersonSlot[P] = S;
}

bool ACityGenLife::ViewPoint(FVector& Out) const
{
	if (const UWorld* W = GetWorld())
	{
		if (APlayerController* PC = W->GetFirstPlayerController())
		{
			if (PC->PlayerCameraManager)
			{
				Out = PC->PlayerCameraManager->GetCameraLocation();
				return true;
			}
		}
	}
	return false;
}

void ACityGenLife::UpdatePeople()
{
	TRACE_CPUPROFILER_EVENT_SCOPE(CityGenLife_UpdatePeople);
	const double T0 = FPlatformTime::Seconds();
	const int32 NP = WalkPos.Num();
	const int32 NC = MidMeshes.Num();
	if (NP == 0 || NC == 0)
	{
		return;
	}
	FVector View;
	if (!ViewPoint(View))
	{
		View = FVector(Center.X * 100.0, -Center.Y * 100.0, 0.0);
	}
	// (lifegen_clothing_toggle: unclothed, the near tier reaches out to MidM, at most NearMax
	// people, so the whole body stands in for the mid meshes' holes too)
	const float Near2 = FMath::Square((Unclothed() && WholeBody ? MidM : NearM) * 100.f);
	const float Mid2 = FMath::Square(MidM * 100.f);
	const float Far2 = FMath::Square(FarM * 100.f);
	// (who is near: the NearMax nearest within NearM; a person already near keeps its slot
	// out to 1.15 NearM, so the edge does not flicker)
	NearCand.Reset();
	// (LG3: a free slot of the pool, or someone in an elevator, is drawn by no tier)
	const bool bCity = IsCity() && WalkState.Num() == NP;
	const bool bMidIdles = HasMidIdles();
	// (people_idles: per person what it plays and since when, so a near sit-down or stand-up
	// starts where the walk processor's clock is, wherever its slot is taken)
	const float TimeNow = (float)GetWorld()->GetTimeSeconds();
	if (PersonAnimPrev.Num() != NP)
	{
		PersonAnimPrev.Init(CgAnim::Walk, NP);
		PersonAnimT.Init(TimeNow, NP);
	}
	for (int32 P = 0; P < NP && P < WalkAnimG.Num(); ++P)
	{
		if (PersonAnimPrev[P] != WalkAnimG[P])
		{
			PersonAnimPrev[P] = WalkAnimG[P];
			PersonAnimT[P] = TimeNow;
		}
	}
	auto Shown = [&](const int32 P)
	{
		return !bCity || WalkState[P] == CgShow::Moving || WalkState[P] == CgShow::Still;
	};
	for (int32 P = 0; P < NP; ++P)
	{
		if (!Shown(P))
		{
			continue;
		}
		const float D2 = FVector::DistSquared(WalkPos[P], View);
		// (LG4: someone sitting is near out to the mid tier: the baked walk has no sitting pose;
		// people_idles: with the idles' bakes the mid tier has one)
		const bool bSit = !bMidIdles && WalkAnimG.IsValidIndex(P) && CgAnim::IsSit(WalkAnimG[P]) && SitClips.Num();
		const float Base = bSit ? FMath::Max(Near2, Mid2) : Near2;
		const float Lim = PersonSlot[P] != INDEX_NONE ? Base * 1.32f : Base;
		if (D2 <= Lim && !WalkPos[P].IsZero())
		{
			NearCand.Emplace(PersonSlot[P] != INDEX_NONE ? D2 * 0.75f : D2, P);
		}
	}
	if (NearCand.Num() > NearMax)
	{
		Algo::Sort(NearCand, [](const TPair<float, int32>& A, const TPair<float, int32>& B) { return A.Key < B.Key; });
		NearCand.SetNum(NearMax);
	}
	TArray<uint8> Want;
	Want.SetNumZeroed(NP);
	for (const TPair<float, int32>& C : NearCand)
	{
		Want[C.Value] = 1;
	}
	for (int32 S = 0; S < NearSlots.Num(); ++S)
	{
		const int32 P = NearSlots[S].Person;
		if (P != INDEX_NONE && (!Want.IsValidIndex(P) || !Want[P]))
		{
			Release(S);
		}
	}
	int32 Free = 0;
	for (const TPair<float, int32>& C : NearCand)
	{
		if (PersonSlot[C.Value] != INDEX_NONE)
		{
			continue;
		}
		while (Free < NearSlots.Num() && NearSlots[Free].Person != INDEX_NONE)
		{
			++Free;
		}
		// (a slot that had the same character is cheaper: no mesh to set; take the first free
		// one otherwise)
		int32 Pick = Free;
		const int32 Ch = PersonChar.IsValidIndex(C.Value) ? PersonChar[C.Value] : 0;
		for (int32 S = Free; S < NearSlots.Num(); ++S)
		{
			if (NearSlots[S].Person == INDEX_NONE && NearSlots[S].Char == Ch)
			{
				Pick = S;
				break;
			}
		}
		if (Pick >= NearMax)
		{
			break;
		}
		Assign(Pick, C.Value);
	}
	NearNow = MidNow = FarNow = 0;
	for (int32 P = 0; P < NP; ++P)
	{
		const int32 C = PersonChar.IsValidIndex(P) ? FMath::Clamp(PersonChar[P], 0, NC - 1) : P % NC;
		const int32 I = PersonInst[P];
		const float Scale = PersonScale.IsValidIndex(P) ? PersonScale[P] : 1.f;
		const FVector At = WalkPos[P];
		const float D2 = FVector::DistSquared(At, View);
		const int32 S = PersonSlot[P];
		uint8 Tier = 3;
		const bool bStill = bCity && WalkState[P] == CgShow::Still;
		if (!Shown(P))
		{
			// (out of the city, or in an elevator: no tier; its slot let go above)
		}
		else if (S != INDEX_NONE)
		{
			Tier = 0;
			if (USkeletalMeshComponent* Lead = NearSlots[S].Comps.Num() ? NearSlots[S].Comps[0] : nullptr)
			{
				// (LG4: at a place slot, its clip: sitting on a bench, a talk clip (talking,
				// smoking, eating), else standing idle; a sitter's root where the bench loop
				// wants it, SitOffset off its point)
				const uint8 Anim = WalkAnimG.IsValidIndex(P) ? WalkAnimG[P] : (uint8)CgAnim::Walk;
				const int32 Group = CharClipGroup.IsValidIndex(C) ? CharClipGroup[C] : 0;
				uint8 ClipWant = bStill ? 1 : 0;
				UAnimSequence* PlaceClip = nullptr;
				if (Anim == CgAnim::Run && !bStill)
				{
					// (LG8: running from a danger: the places' run clip, else its walk faster)
					ClipWant = 200;
					PlaceClip = RunClips.IsValidIndex(Group) ? RunClips[Group].Get() : nullptr;
				}
				else if (Anim >= CgAnim::SitDown && SitInCount > 0 && SitInClips.IsValidIndex(Group * SitInCount + (Anim - CgAnim::SitDown)) &&
					SitInClips[Group * SitInCount + (Anim - CgAnim::SitDown)])
				{
					// (people_idles: sitting down, the sit-down from the side it came, once)
					ClipWant = (uint8)(10 + (Anim - CgAnim::SitDown));
					PlaceClip = SitInClips[Group * SitInCount + (Anim - CgAnim::SitDown)].Get();
				}
				else if (Anim == CgAnim::StandUp && SitOutClips.IsValidIndex(Group) && SitOutClips[Group])
				{
					// (people_idles: standing up and walking off, once)
					ClipWant = 9;
					PlaceClip = SitOutClips[Group].Get();
				}
				else if (CgAnim::IsSit(Anim) && SitClips.IsValidIndex(Group) && SitClips[Group])
				{
					ClipWant = 2;
					PlaceClip = SitClips[Group].Get();
				}
				else if (Anim == CgAnim::Talk && TalkCount > 0 && TalkClips.IsValidIndex(Group * TalkCount))
				{
					const int32 K = (int32)((uint32)(PersonSeed.IsValidIndex(P) ? PersonSeed[P] : P) % (uint32)TalkCount);
					ClipWant = (uint8)(3 + K);
					PlaceClip = TalkClips[Group * TalkCount + K].Get();
				}
				else if (Anim != CgAnim::Walk)
				{
					ClipWant = 1;
				}
				FVector Root = At;
				// (the sit-downs and the stand-up are in the seat's frame, as the loop)
				const bool bOnce = ClipWant == 9 || (ClipWant >= 10 && ClipWant < 200);
				if (ClipWant == 2 || bOnce)
				{
					const FVector Fwd(FMath::Cos(FMath::DegreesToRadians(WalkYaw[P])), FMath::Sin(FMath::DegreesToRadians(WalkYaw[P])), 0.0);
					Root += Fwd * SitOffset.X + FVector(0.0, 0.0, SitOffset.Y);
				}
				// (people_surfaces: where the body stood, so the clip before is drawn there through
				// a crossfade while the mesh moves to a seat)
				const FTransform Was = Lead->GetComponentTransform();
				Lead->SetWorldLocationAndRotation(Root, FRotator(0.f, WalkYaw[P] + MeshYaw, 0.f), false, nullptr, ETeleportType::TeleportPhysics);
				Lead->SetWorldScale3D(FVector(Scale));
				UCgPersonAnim* Body = PersonAnimOf(Lead);
				// (umbrella_hold: the arm up while its umbrella is open, down as it folds)
				if (Body)
				{
					Body->HoldTarget = UmbOpen(P) ? 1.f : 0.f;
				}
				const uint8 ClipWas = NearSlots[S].Clip;
				const bool bFresh = NearSlots[S].bFresh;
				NearSlots[S].bFresh = false;
				// (people_surfaces: the crossfade into the new clip: none for a person just come
				// near; SitBlendS into the sitting loop after a sit-down and from the loop into
				// the stand-up (the pop as a sitter rose), ClipBlendS otherwise)
				const bool bSitBlend = (ClipWant == 2 && ClipWas >= 10 && ClipWas < 200) || (ClipWant == 9 && ClipWas == 2);
				const float BlendS = bFresh ? 0.f : (bSitBlend ? SitBlendS : ClipBlendS);
				const FTransform Fix = Was.GetRelativeTransform(Lead->GetComponentTransform());
				// (LG3: standing, at a signal or behind someone: the idle; walking, the walk)
				if (bCity && Body && ClipWas != ClipWant && ClipWant == 200)
				{
					// (LG8: the run: its clip at the runner's speed over the clip's own, else the walk
					// at the flight's pace)
					const int32 Gait = PersonGait.IsValidIndex(P) ? FMath::Clamp(PersonGait[P], 0, FMath::Max(0, Gaits - 1)) : 0;
					const int32 G = FMath::Clamp(Group * FMath::Max(1, Gaits) + Gait, 0, FMath::Max(0, WalkClips.Num() - 1));
					UAnimSequence* Clip = PlaceClip ? PlaceClip : (WalkClips.IsValidIndex(G) ? WalkClips[G].Get() : nullptr);
					if (Clip)
					{
						const float V = (PersonPace.IsValidIndex(P) ? PersonPace[P] : 1.35f) * FleePace * PaceNow;
						Body->Play(Clip, true, PlaceClip ? FMath::Clamp(V / FMath::Max(1.f, RunClipSpeed), 0.6f, 1.5f) : FMath::Clamp(WalkRate(P) * FleePace, 0.5f, 3.f),
							0.f, BlendS, Fix);
						NearSlots[S].Gait = INDEX_NONE;
					}
					NearSlots[S].Clip = ClipWant;
				}
				else if (bCity && Body && ClipWas != ClipWant)
				{
					const bool bStand = ClipWant != 0;
					UAnimSequence* Clip = PlaceClip;
					if (!Clip && bStand && IdleClips.Num())
					{
						Clip = IdleClips[(PersonGait.IsValidIndex(P) ? PersonGait[P] : 0) % IdleClips.Num()].Get();
					}
					if (bStand && Clip && bOnce)
					{
						// (people_idles: a sit-down or the stand-up once, from where the walk
						// processor's clock has it: since it began)
						// (a sit-down from its stretch's start: the clip's walk up is the person's own)
						const float Len = FMath::Max(0.1f, Clip->GetPlayLength());
						const int32 In = Group * SitInCount + (ClipWant - 10);
						const float From = ClipWant >= 10 && SitInStart.IsValidIndex(In) ? SitInStart[In] : 0.f;
						Body->Play(Clip, false, 1.f,
							FMath::Clamp(From + TimeNow - (PersonAnimT.IsValidIndex(P) ? PersonAnimT[P] : TimeNow), 0.f, Len), BlendS, Fix);
						NearSlots[S].Gait = INDEX_NONE;
					}
					else if (bStand && Clip)
					{
						// (each its own place in the loop, so a bench's two sitters or a gang's
						// ring do not move as one; people_idles: one who just sat down from the
						// loop's start, where its sit-down ends)
						const bool bSatDown = ClipWant == 2 && ClipWas >= 10 && ClipWas < 200;
						Body->Play(Clip, true, 1.f,
							bSatDown ? 0.f : FMath::Fmod(PhaseOffset(P) * 1.7f, FMath::Max(0.1f, Clip->GetPlayLength())), BlendS, Fix);
						NearSlots[S].Gait = INDEX_NONE;
					}
					else if (!bStand)
					{
						const int32 Gait = PersonGait.IsValidIndex(P) ? FMath::Clamp(PersonGait[P], 0, FMath::Max(0, Gaits - 1)) : 0;
						const int32 G = FMath::Clamp(Group * FMath::Max(1, Gaits) + Gait, 0, FMath::Max(0, WalkClips.Num() - 1));
						if (UAnimSequence* Walk = WalkClips.IsValidIndex(G) ? WalkClips[G].Get() : nullptr)
						{
							Body->Play(Walk, true, WalkRate(P), 0.f, BlendS, Fix);
							NearSlots[S].Gait = G;
						}
					}
					NearSlots[S].Clip = ClipWant;
				}
			}
			++NearNow;
		}
		else if (D2 <= Mid2 && !At.IsZero())
		{
			Tier = 1;
			++MidNow;
		}
		else if (D2 <= Far2 && !At.IsZero())
		{
			Tier = 2;
			++FarNow;
		}
		// (LG3: a mid or far person standing still holds its walk's frame)
		// (LG8: running from a danger, its walk played faster: 2)
		// (people_idles: sitting, the baked sitting loop and a sitting cell)
		const uint8 AnimP = WalkAnimG.IsValidIndex(P) ? WalkAnimG[P] : (uint8)CgAnim::Walk;
		// (people_surfaces: sitting as the near tier would be: standing through a sit-down until
		// the near clip has the person seated, sitting through a stand-up until it is up; and
		// standing where the near clip has the body: at the sit-down's start, at the stand-up's
		// end)
		bool bSeated = CgAnim::IsSit(AnimP);
		FVector AtTier = At;
		float YawTier = WalkYaw[P];
		const float Since = PersonAnimT.IsValidIndex(P) ? TimeNow - PersonAnimT[P] : 0.f;
		if (AnimP >= CgAnim::SitDown && SitSeatedS.IsValidIndex(AnimP - CgAnim::SitDown))
		{
			const int32 K = AnimP - CgAnim::SitDown;
			bSeated = Since >= SitSeatedS[K];
			if (!bSeated && bStill && SitInSeat.IsValidIndex(4 * K + 2))
			{
				AtTier += FRotator(0.f, WalkYaw[P], 0.f).RotateVector(FVector(SitInSeat[4 * K], SitInSeat[4 * K + 1], 0.f));
				YawTier += SitInSeat[4 * K + 2];
			}
		}
		else if (AnimP == CgAnim::StandUp && SitSeatedS.Num())
		{
			bSeated = Since < SitRiseS;
			if (!bSeated && bStill && SitOutSeat.IsValidIndex(2))
			{
				AtTier += FRotator(0.f, WalkYaw[P], 0.f).RotateVector(FVector(SitOutSeat[0], SitOutSeat[1], 0.f));
				YawTier += SitOutSeat[2];
			}
		}
		// (the mid mesh is the skeletal meshes' frame, MeshYaw off the walk; the card's frame
		// has the person facing +X, as its sheet was drawn)
		MidXf[C][I] = Tier == 1 ? FTransform(FRotator(0.f, YawTier + MeshYaw, 0.f), AtTier, FVector(Scale)) : Hidden;
		FarXf[C][I] = Tier == 2 ? FTransform(FRotator(0.f, YawTier, 0.f), AtTier, FVector(Scale)) : Hidden;
		PersonTier[P] = Tier;
		uint8 Look = bStill ? (bSeated ? CgLook::Sit : CgLook::Still) : (AnimP == CgAnim::Run ? CgLook::Run : CgLook::Walk);
		// (umbrella_hold: a mid person whose umbrella is open plays its bake's loops with the arm held)
		if (Tier == 1 && (Look == CgLook::Walk || Look == CgLook::Still) && HasMidUmb() && UmbOpen(P))
		{
			Look = (uint8)(Look | CgLook::Umb);
		}
		if (bCity && (Tier == 1 || Tier == 2) && PersonStill.IsValidIndex(P) && PersonStill[P] != Look)
		{
			PersonStill[P] = Look;
			ApplyLook(P, Look);
		}
	}
	// (LG3: the far cards move half as often, each character's every second frame; a
	// character with nobody drawn in a tier, now or the frame before, is not sent again)
	if (FarSeen.Num() != NC)
	{
		FarSeen.Init(1, NC);
		MidSeen.Init(1, NC);
	}
	for (int32 K = 0; K < NC; ++K)
	{
		auto Any = [](const TArray<FTransform>& Xs)
		{
			for (const FTransform& X : Xs)
			{
				if (X.GetScale3D().X > 0.0)
				{
					return true;
				}
			}
			return false;
		};
		if (MidComps.IsValidIndex(K) && MidComps[K] && MidXf[K].Num())
		{
			const uint8 Now = Any(MidXf[K]) ? 1 : 0;
			if (Now || MidSeen[K])
			{
				MidComps[K]->BatchUpdateInstancesTransforms(0, MidXf[K], false, bRebuildRenderState, false);
			}
			MidSeen[K] = Now;
		}
		// (LG8: every third frame: a far card 90 to 300 m off moves a few centimeters a frame)
		if (FarComps.IsValidIndex(K) && FarComps[K] && FarXf[K].Num() && (!bCity || ((Ticks + K) % 3) == 0 || !FarSeen[K]))
		{
			const uint8 Now = Any(FarXf[K]) ? 1 : 0;
			if (Now || FarSeen[K])
			{
				FarComps[K]->BatchUpdateInstancesTransforms(0, FarXf[K], false, bRebuildRenderState, false);
			}
			FarSeen[K] = Now;
		}
	}
	const double Ms = (FPlatformTime::Seconds() - T0) * 1000.0;
	PeopleMs = PeopleMs > 0.0 ? 0.98 * PeopleMs + 0.02 * Ms : Ms;
}
