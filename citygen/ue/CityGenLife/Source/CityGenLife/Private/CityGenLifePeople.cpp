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

#include "CityGenLifeActor.h"
#include "Algo/Sort.h"
#include "Animation/AnimSequence.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "HAL/PlatformTime.h"
#include "Materials/MaterialInterface.h"

namespace
{
	constexpr int32 MidFloats = 7;     // time offset, play rate, first frame, last frame, tint rgb
	constexpr int32 FarFloats = 5;     // time offset, cycles a second, tint rgb
	const FTransform Hidden(FQuat::Identity, FVector(0.0, 0.0, -1.0e6), FVector(0.0));

	uint32 Mix(uint32 X)
	{
		X ^= X >> 16; X *= 0x7feb352du; X ^= X >> 15; X *= 0x846ca68bu; X ^= X >> 16;
		return X;
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
	const float Pace = PersonPace.IsValidIndex(P) ? PersonPace[P] : 1.35f;
	return FMath::Clamp(Pace / ClipV, 0.5f, 2.0f);
}

float ACityGenLife::PhaseOffset(const int32 P) const
{
	const uint32 S = PersonSeed.IsValidIndex(P) ? (uint32)PersonSeed[P] : Mix((uint32)P + 17u);
	return (Mix(S) % 10000u) / 1000.f;      // seconds, 0 to 10
}

void ACityGenLife::MakePeople()
{
	const int32 NC = MidMeshes.Num();
	MidComps.Reset();
	FarComps.Reset();
	auto Make = [this](const FString& Name, UStaticMesh* Mesh, UMaterialInterface* Mat, const int32 Floats, const bool bShadow, const float CullM)
	{
		UInstancedStaticMeshComponent* C = NewObject<UInstancedStaticMeshComponent>(this, *Name);
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
		return C;
	};
	for (int32 K = 0; K < NC; ++K)
	{
		MidComps.Add(MidMeshes[K] ? Make(FString::Printf(TEXT("PeopleMid%d"), K), MidMeshes[K], nullptr, MidFloats, bShadows, MidM + 20.f) : nullptr);
		UMaterialInterface* Card = CardMaterials.IsValidIndex(K) ? CardMaterials[K].Get() : nullptr;
		FarComps.Add(CardMesh ? Make(FString::Printf(TEXT("PeopleFar%d"), K), CardMesh, Card, FarFloats, false, FarM + 20.f) : nullptr);
	}
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
	TArray<float> Data;
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
		const float Rate = WalkRate(P);
		const float T0 = PhaseOffset(P);
		const float Tint[3] = {
			PersonTint.IsValidIndex(3 * P) ? PersonTint[3 * P] : 0.5f,
			PersonTint.IsValidIndex(3 * P + 1) ? PersonTint[3 * P + 1] : 0.5f,
			PersonTint.IsValidIndex(3 * P + 2) ? PersonTint[3 * P + 2] : 0.5f};
		if (UInstancedStaticMeshComponent* Mid = MidComps.IsValidIndex(C) ? MidComps[C].Get() : nullptr)
		{
			const float First = MidFrames.IsValidIndex(4 * C) ? MidFrames[4 * C] : 0.f;
			const float Last = MidFrames.IsValidIndex(4 * C + 1) ? MidFrames[4 * C + 1] : 0.f;
			Data = {T0, Rate, First, Last, Tint[0], Tint[1], Tint[2]};
			Mid->SetCustomData(PersonInst[P], Data, false);
		}
		if (UInstancedStaticMeshComponent* Far = FarComps.IsValidIndex(C) ? FarComps[C].Get() : nullptr)
		{
			const float Cycle = MidFrames.IsValidIndex(4 * C + 3) && MidFrames[4 * C + 3] > 0.05f ? MidFrames[4 * C + 3] : 1.f;
			Data = {T0, Rate / Cycle, Tint[0], Tint[1], Tint[2]};
			Far->SetCustomData(PersonInst[P], Data, false);
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
			Comp->SetSkeletalMesh(Mesh, false);
			if (K > 0)
			{
				Comp->SetLeaderPoseComponent(Mesh ? Lead : nullptr);
			}
		}
		Slot.Char = C;
		Slot.Gait = INDEX_NONE;
	}
	const int32 G = PersonGait.IsValidIndex(P) ? FMath::Clamp(PersonGait[P], 0, FMath::Max(0, WalkClips.Num() - 1)) : 0;
	UAnimSequence* Clip = WalkClips.IsValidIndex(G) ? WalkClips[G].Get() : nullptr;
	if (Clip && Slot.Gait != G)
	{
		Lead->SetAnimationMode(EAnimationMode::AnimationSingleNode);
		Lead->PlayAnimation(Clip, true);
		Slot.Gait = G;
	}
	const float Rate = WalkRate(P);
	Lead->SetPlayRate(Rate);
	if (Clip)
	{
		// (in phase with its baked walk: the same time offset and rate)
		const float Len = FMath::Max(0.1f, Clip->GetPlayLength());
		const float T = (float)GetWorld()->GetTimeSeconds() + PhaseOffset(P);
		Lead->SetPosition(FMath::Fmod(T * Rate, Len), false);
	}
	for (USkeletalMeshComponent* Comp : Slot.Comps)
	{
		const bool bOn = Comp->GetSkeletalMeshAsset() != nullptr;
		Comp->SetVisibility(bOn);
		Comp->SetComponentTickEnabled(bOn);
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
	const float Near2 = FMath::Square(NearM * 100.f);
	const float Mid2 = FMath::Square(MidM * 100.f);
	const float Far2 = FMath::Square(FarM * 100.f);
	// (who is near: the NearMax nearest within NearM; a person already near keeps its slot
	// out to 1.15 NearM, so the edge does not flicker)
	NearCand.Reset();
	for (int32 P = 0; P < NP; ++P)
	{
		const float D2 = FVector::DistSquared(WalkPos[P], View);
		const float Lim = PersonSlot[P] != INDEX_NONE ? Near2 * 1.32f : Near2;
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
		if (S != INDEX_NONE)
		{
			Tier = 0;
			if (USkeletalMeshComponent* Lead = NearSlots[S].Comps.Num() ? NearSlots[S].Comps[0] : nullptr)
			{
				Lead->SetWorldLocationAndRotation(At, FRotator(0.f, WalkYaw[P] + MeshYaw, 0.f), false, nullptr, ETeleportType::TeleportPhysics);
				Lead->SetWorldScale3D(FVector(Scale));
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
		const FTransform Xf(FRotator(0.f, WalkYaw[P], 0.f), At, FVector(Scale));
		MidXf[C][I] = Tier == 1 ? Xf : Hidden;
		FarXf[C][I] = Tier == 2 ? Xf : Hidden;
		PersonTier[P] = Tier;
	}
	for (int32 K = 0; K < NC; ++K)
	{
		if (MidComps.IsValidIndex(K) && MidComps[K] && MidXf[K].Num())
		{
			MidComps[K]->BatchUpdateInstancesTransforms(0, MidXf[K], false, bRebuildRenderState, false);
		}
		if (FarComps.IsValidIndex(K) && FarComps[K] && FarXf[K].Num())
		{
			FarComps[K]->BatchUpdateInstancesTransforms(0, FarXf[K], false, bRebuildRenderState, false);
		}
	}
	const double Ms = (FPlatformTime::Seconds() - T0) * 1000.0;
	PeopleMs = PeopleMs > 0.0 ? 0.98 * PeopleMs + 0.02 * Ms : Ms;
}
