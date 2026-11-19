// people_surfaces: a near person's animation (docs/unreal_export.md, "People on their surfaces").
//
// What LG1 to people_idles played on a near person's body as a single node (one clip, looping
// or once, at a rate, from a position), with a crossfade from the clip before: a person
// rising from a bench blends from the sitting loop into the stand-up instead of jumping to
// the stand-up's first pose (single node animation has no blend). The clip before keeps
// playing through the blend where the person stood: a sit-down and a stand-up play in the
// seat's frame, so the mesh moves to the seat as one begins and the clip before is carried
// back to where it was (`RootFix`, the old component transform in the new one's frame,
// applied to its root bone and faded out with it).
// umbrella_hold: a person holding an umbrella has its right arm held over whatever plays (the
// group's held pose, `people_places.py` `hold_pose`), weighted in and out as it opens and folds.

#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "CityGenLifeAnim.generated.h"

class UAnimSequenceBase;

/** The proxy: samples the clip (and the clip before, weighted out over the blend) on any
 *  thread; its state copied from the instance on the game thread (PreUpdate). */
struct FCgPersonAnimProxy : public FAnimInstanceProxy
{
	FCgPersonAnimProxy() = default;
	explicit FCgPersonAnimProxy(UAnimInstance* InInstance) : FAnimInstanceProxy(InInstance) {}

	virtual void PreUpdate(UAnimInstance* InAnimInstance, float DeltaSeconds) override;
	virtual bool Evaluate(FPoseContext& Output) override;

	UAnimSequenceBase* Cur = nullptr;
	UAnimSequenceBase* Prev = nullptr;
	float CurT = 0.f;
	float PrevT = 0.f;
	bool bCurLoop = true;
	bool bPrevLoop = true;
	float CurWeight = 1.f;
	FTransform Fix = FTransform::Identity;
	// (umbrella_hold: the held arm and its weight)
	TArray<int32> HoldBones;
	TArray<FQuat> HoldRots;
	float HoldWeight = 0.f;
};

UCLASS(transient, NotBlueprintable)
class CITYGENLIFE_API UCgPersonAnim : public UAnimInstance
{
	GENERATED_BODY()

public:
	/** Play a clip from `Position` (s) at `Rate`, looping or once (held on its last frame);
	 *  over `BlendS` (s; 0: at once) from what played, that clip's root moved by `RootFix`. */
	void Play(UAnimSequenceBase* Clip, bool bLoop, float Rate, float Position, float BlendS,
		const FTransform& RootFix = FTransform::Identity);
	void SetRate(float Rate) { CurRate = Rate; }
	void SetTime(float Position) { CurT = Position; }
	UAnimSequenceBase* Clip() const { return Cur; }
	/** The clips' times on by the frame's delta, the blend's weight (the proxy's PreUpdate). */
	void Advance(float DeltaSeconds);
	float CurWeight() const;

	UPROPERTY(Transient) TObjectPtr<UAnimSequenceBase> Cur;
	UPROPERTY(Transient) TObjectPtr<UAnimSequenceBase> Prev;
	float CurT = 0.f, CurRate = 1.f, PrevT = 0.f, PrevRate = 1.f;
	float BlendS = 0.f, BlendT = 0.f;
	bool bCurLoop = true, bPrevLoop = true;
	FTransform Fix = FTransform::Identity;

	/** umbrella_hold: the right arm holding an umbrella, layered over whatever clip plays: the
	 *  rotations `HoldRots` of the bones `HoldBones` (skeleton indices: the upper arm, forearm
	 *  and hand) in their parents' frames, the clip's own past them; weighted toward
	 *  `HoldTarget` (0 or 1) over `HoldS` seconds, eased (`HoldWeight`). */
	void SetHold(const TArray<int32>& Bones, const TArray<FQuat>& Rots) { HoldBones = Bones; HoldRots = Rots; }
	float HoldWeight() const;
	TArray<int32> HoldBones;
	TArray<FQuat> HoldRots;
	float HoldTarget = 0.f, HoldW = 0.f, HoldS = 0.35f;

protected:
	virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;
};
