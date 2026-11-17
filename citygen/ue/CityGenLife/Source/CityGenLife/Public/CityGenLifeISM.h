// lifegen's instanced components (LG8's performance pass): the engine's instanced static mesh
// component with fixed bounds. Every moving instanced component of the life controller (the
// people's mid meshes and cards, the cars' parts, the trains, what flies and floats, the
// umbrellas) is sent new transforms most frames; the engine's component then measures its
// bounds again over every instance it has (UInstancedStaticMeshComponent::CalcBoundsImpl: 1.2 ms
// of the game thread a frame on Delta's walk, 234 components). Their instances are culled one
// by one on the GPU, so a component's bounds only need to hold them all: the city's box, set
// once (`SetFixedBounds`), and measured never.

#pragma once

#include "CoreMinimal.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "CityGenLifeISM.generated.h"

UCLASS()
class CITYGENLIFE_API UCgLifeISM : public UInstancedStaticMeshComponent
{
	GENERATED_BODY()

public:
	/** The box (world, UE cm) every instance of it stays within; an empty box: the engine's own
	 *  bounds over its instances. */
	void SetFixedBounds(const FBox& InBox)
	{
		Fixed = InBox;
		UpdateBounds();
		MarkRenderTransformDirty();
	}

	virtual FBoxSphereBounds CalcBounds(const FTransform& LocalToWorld) const override
	{
		if (Fixed.IsValid)
		{
			return FBoxSphereBounds(Fixed);
		}
		return Super::CalcBounds(LocalToWorld);
	}

private:
	FBox Fixed = FBox(ForceInit);
};
