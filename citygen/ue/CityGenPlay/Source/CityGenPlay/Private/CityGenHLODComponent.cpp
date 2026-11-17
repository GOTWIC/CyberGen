// The instanced HLODs' component: a visibility flip without a new render state (see the
// header).

#include "CityGenHLODComponent.h"

#include "Engine/World.h"
#include "HAL/IConsoleManager.h"
#include "PrimitiveSceneInfo.h"
#include "PrimitiveSceneProxy.h"
#include "RenderingThread.h"
#include "SceneInterface.h"
#include "WorldPartition/HLOD/HLODActor.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(CityGenHLODComponent)

DEFINE_LOG_CATEGORY_STATIC(LogCityGenHLOD, Log, All);

namespace
{
	int32 GCityGenHLODFast = 1;
	FAutoConsoleVariableRef CVarCityGenHLODFast(
		TEXT("CityGen.HLODFastVisibility"), GCityGenHLODFast,
		TEXT("1 (default): an instanced HLOD component hidden or shown as its cell streams keeps ")
		TEXT("its scene proxy and only flips whether it is drawn (read when an HLOD actor starts ")
		TEXT("playing and at each flip); 0: the engine's way, its render state recreated ")
		TEXT("(instances and materials sent again)."));

	FAutoConsoleCommand CmdCityGenHLODStatus(
		TEXT("CityGen.HLODStatus"),
		TEXT("The instanced HLOD components' visibility flips since the start: in place, and by a ")
		TEXT("new render state (and why)."),
		FConsoleCommandDelegate::CreateLambda([]()
		{
			const int64* W = UCityGenHLODComponent::SlowWhy;
			UE_LOG(LogCityGenHLOD, Display, TEXT("CityGen.HLODStatus fast=%d in_place=%lld recreated=%lld ")
				TEXT("(off %lld, not a game %lld, no render state %lld, dirty %lld, no proxy hidden %lld, ")
				TEXT("no proxy shown %lld) detached=%lld"),
				GCityGenHLODFast, UCityGenHLODComponent::FastFlips, UCityGenHLODComponent::SlowFlips,
				W[0], W[1], W[2], W[3], W[4], W[5], UCityGenHLODComponent::Detached);
		}));
}

int64 UCityGenHLODComponent::FastFlips = 0;
int64 UCityGenHLODComponent::SlowFlips = 0;
int64 UCityGenHLODComponent::SlowWhy[6] = {0, 0, 0, 0, 0, 0};
int64 UCityGenHLODComponent::Detached = 0;

UCityGenHLODComponent::UCityGenHLODComponent(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
}

void UCityGenHLODComponent::BeginPlay()
{
	Super::BeginPlay();
	// The HLOD actor makes one of its components the root and attaches the rest to it, and a
	// component whose visibility changes marks the render state of everything attached to it
	// dirty (USceneComponent::SetVisibility, EVisibilityPropagation::DirtyOnly): the root's
	// flip had every other component of the actor made anew, whatever each one's own flip
	// did. Each flips its own visibility (AWorldPartitionHLOD::SetVisibility), so in a game
	// they stand alone, each where it is. (The actor starts playing before World Partition's
	// HLOD subsystem first shows or hides it.)
	const UWorld* World = GetWorld();
	USceneComponent* Parent = GetAttachParent();
	if (GCityGenHLODFast != 0 && World != nullptr && World->IsGameWorld() && Parent != nullptr &&
		Parent->GetOwner() == GetOwner() && Cast<AWorldPartitionHLOD>(GetOwner()) != nullptr)
	{
		DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
		++Detached;
	}
}

void UCityGenHLODComponent::OnVisibilityChanged()
{
	const UWorld* World = GetWorld();
	FPrimitiveSceneProxy* Proxy = SceneProxy;
	// (only in a game: the editor draws HLODs its own way; and only with a proxy to keep: a
	// component hidden when its render state was made has none, and is made anew once; one
	// already marked dirty is made anew anyway)
	const int32 Why = GCityGenHLODFast == 0 ? 0
		: (World == nullptr || !World->IsGameWorld()) ? 1
		: !IsRenderStateCreated() ? 2
		: IsRenderStateDirty() ? 3
		: Proxy == nullptr ? (IsVisible() ? 5 : 4)
		: -1;
	if (Why >= 0)
	{
		++SlowFlips;
		++SlowWhy[Why];
		Super::OnVisibilityChanged();
		return;
	}
	++FastFlips;
	const bool bDrawn = IsVisible();
	// (commands run in order: the proxy is not removed before this one runs, since its
	// removal is queued after it, when the component lets the proxy go)
	ENQUEUE_RENDER_COMMAND(CityGenHLODVisibility)(
		[Proxy, bDrawn](FRHICommandListBase&)
		{
			FPrimitiveSceneInfo* Info = Proxy->GetPrimitiveSceneInfo();
			if (Info != nullptr && Info->IsIndexValid())
			{
				FPrimitiveSceneProxy* One = Proxy;
				Proxy->GetScene().UpdatePrimitivesIsDrawn_RenderThread(MakeArrayView(&One, 1), bDrawn);
			}
			else
			{
				// (still waiting to be added to the scene: the flags it is added with)
				Proxy->SetIsDrawn_RenderThread(bDrawn);
			}
		});
}
