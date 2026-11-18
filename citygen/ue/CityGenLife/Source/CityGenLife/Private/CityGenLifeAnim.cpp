// people_surfaces: a near person's animation with a crossfade (CityGenLifeAnim.h).

#include "CityGenLifeAnim.h"
#include "AnimationRuntime.h"
#include "Animation/AnimNodeBase.h"
#include "Animation/AnimSequenceBase.h"
#include "Animation/AnimationAsset.h"
#include "Animation/AnimationPoseData.h"

namespace
{
	void Step(const UAnimSequenceBase* S, float& T, const float Rate, const bool bLoop, const float Dt)
	{
		if (!S)
		{
			return;
		}
		const float Len = FMath::Max(S->GetPlayLength(), 1e-3f);
		T += Dt * Rate;
		if (bLoop)
		{
			T = FMath::Fmod(T, Len);
			if (T < 0.f)
			{
				T += Len;
			}
		}
		else
		{
			T = FMath::Clamp(T, 0.f, Len);
		}
	}

	void Sample(const UAnimSequenceBase* S, const float T, const bool bLoop, FPoseContext& Out)
	{
		FAnimationPoseData Data(Out);
		S->GetAnimationPose(Data, FAnimExtractContext(static_cast<double>(T), false, FDeltaTimeRecord(), bLoop));
	}
}

void UCgPersonAnim::Play(UAnimSequenceBase* Clip, const bool bLoop, const float Rate, const float Position,
	const float InBlendS, const FTransform& RootFix)
{
	if (InBlendS > 0.f && Cur && Clip)
	{
		// (what played goes on under the new clip, weighted out; a blend cut short starts from
		// the clip that was coming in)
		Prev = Cur;
		PrevT = CurT;
		PrevRate = CurRate;
		bPrevLoop = bCurLoop;
		Fix = RootFix;
		BlendS = InBlendS;
		BlendT = 0.f;
	}
	else
	{
		Prev = nullptr;
		BlendS = BlendT = 0.f;
		Fix = FTransform::Identity;
	}
	Cur = Clip;
	bCurLoop = bLoop;
	CurRate = Rate;
	CurT = Position;
}

void UCgPersonAnim::Advance(const float Dt)
{
	Step(Cur, CurT, CurRate, bCurLoop, Dt);
	// (umbrella_hold: the held arm's weight toward its target)
	const float Rate = Dt / FMath::Max(0.01f, HoldS);
	HoldW = HoldTarget > HoldW ? FMath::Min(HoldTarget, HoldW + Rate) : FMath::Max(HoldTarget, HoldW - Rate);
	if (Prev)
	{
		Step(Prev, PrevT, PrevRate, bPrevLoop, Dt);
		BlendT += Dt;
		if (BlendT >= BlendS)
		{
			Prev = nullptr;
		}
	}
}

float UCgPersonAnim::CurWeight() const
{
	if (!Prev || BlendS <= 0.f)
	{
		return 1.f;
	}
	// (eased in and out: the blend starts and ends without a kink)
	const float U = FMath::Clamp(BlendT / BlendS, 0.f, 1.f);
	return U * U * (3.f - 2.f * U);
}

float UCgPersonAnim::HoldWeight() const
{
	const float U = FMath::Clamp(HoldW, 0.f, 1.f);
	return U * U * (3.f - 2.f * U);
}

FAnimInstanceProxy* UCgPersonAnim::CreateAnimInstanceProxy()
{
	return new FCgPersonAnimProxy(this);
}

void FCgPersonAnimProxy::PreUpdate(UAnimInstance* InAnimInstance, const float DeltaSeconds)
{
	FAnimInstanceProxy::PreUpdate(InAnimInstance, DeltaSeconds);
	if (UCgPersonAnim* A = Cast<UCgPersonAnim>(InAnimInstance))
	{
		A->Advance(DeltaSeconds);
		Cur = A->Cur.Get();
		Prev = A->Prev.Get();
		CurT = A->CurT;
		PrevT = A->PrevT;
		bCurLoop = A->bCurLoop;
		bPrevLoop = A->bPrevLoop;
		CurWeight = A->CurWeight();
		Fix = A->Fix;
		HoldWeight = A->HoldWeight();
		if (HoldWeight > 0.f)
		{
			HoldBones = A->HoldBones;
			HoldRots = A->HoldRots;
		}
	}
}

bool FCgPersonAnimProxy::Evaluate(FPoseContext& Output)
{
	if (!Cur || !Cur->GetSkeleton())
	{
		Output.ResetToRefPose();
		return true;
	}
	Sample(Cur, CurT, bCurLoop, Output);
	if (Prev && Prev->GetSkeleton() && CurWeight < 1.f)
	{
		FPoseContext Old(Output);
		Sample(Prev, PrevT, bPrevLoop, Old);
		// (the clip before where the person stood: its root bone, in the component's frame,
		// carried from the old component transform to the new one's)
		if (Old.Pose.GetNumBones() > 0)
		{
			const FCompactPoseBoneIndex Root(0);
			Old.Pose[Root] = Old.Pose[Root] * Fix;
		}
		FAnimationPoseData Out(Output);
		const FAnimationPoseData From(Old);
		FAnimationRuntime::BlendTwoPosesTogetherInPlace(Out, From, CurWeight);
	}
	// (umbrella_hold: the arm holding an umbrella over what plays, from the upper arm down; the
	// shoulder (clavicle) and every bone past the hand the clip's)
	if (HoldWeight > 0.f && HoldBones.Num() == HoldRots.Num())
	{
		const FBoneContainer& BC = Output.Pose.GetBoneContainer();
		for (int32 K = 0; K < HoldBones.Num(); ++K)
		{
			const FCompactPoseBoneIndex CI = BC.GetCompactPoseIndexFromSkeletonPoseIndex(FSkeletonPoseBoneIndex(HoldBones[K]));
			if (CI.IsValid() && CI.GetInt() < Output.Pose.GetNumBones())
			{
				FTransform& T = Output.Pose[CI];
				T.SetRotation(FQuat::Slerp(T.GetRotation(), HoldRots[K], HoldWeight).GetNormalized());
			}
		}
	}
	return true;
}
