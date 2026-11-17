// lifegen's instanced components (LG8's performance pass): the engine's instanced static mesh
// component with fixed bounds. Every moving instanced component of the life controller (the
// people's mid meshes and cards, the cars' parts, the trains, what flies and floats, the
// umbrellas) is sent new transforms most frames; the engine's component then measures its
// bounds again over every instance it has (UInstancedStaticMeshComponent::CalcBoundsImpl: 1.2 ms
// of the game thread a frame on Delta's walk, 234 components). Their instances are culled one
// by one on the GPU, so a component's bounds only need to hold them all. `CityGenLife.Bounds`:
// 1 (the default) the city's box, set once (`SetFixedBounds`), measured never: every component
// is drawn in every view (twice LG7's draw calls), which the render thread and the GPU carry
// at no cost on Delta, while the game thread, the bound, saves the measure (1.7 ms of game time
// at the 95th percentile against 2 on the lean route); 2 lifegen's own measure (each shown
// instance's place, the mesh's radius times the instance's largest scale; hidden instances,
// scaled to nothing or sunk a kilometer under, left out), a component none of whose instances
// is in a view culled for it, but every instance read each frame; 0 the engine's own.

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

	/** How the bounds are measured: 0 the engine's way, 1 the fixed box (the default), 2
	 *  lifegen's own. */
	static int32 BoundsMode;

	virtual FBoxSphereBounds CalcBounds(const FTransform& LocalToWorld) const override
	{
		if (BoundsMode == 1 && Fixed.IsValid)
		{
			return FBoxSphereBounds(Fixed);
		}
		if (BoundsMode == 2 && GetStaticMesh())
		{
			return Measure(LocalToWorld);
		}
		return Super::CalcBounds(LocalToWorld);
	}

private:
	FBox Fixed = FBox(ForceInit);

	FBoxSphereBounds Measure(const FTransform& LocalToWorld) const
	{
		const FBoxSphereBounds Mesh = GetStaticMesh()->GetBounds();
		FVector Lo(UE_BIG_NUMBER), Hi(-UE_BIG_NUMBER);
		double MaxS2 = 0.0;
		for (const FInstancedStaticMeshInstanceData& D : PerInstanceSMData)
		{
			const FMatrix& M = D.Transform;
			const double S2 = FMath::Max3(M.M[0][0] * M.M[0][0] + M.M[0][1] * M.M[0][1] + M.M[0][2] * M.M[0][2],
				M.M[1][0] * M.M[1][0] + M.M[1][1] * M.M[1][1] + M.M[1][2] * M.M[1][2],
				M.M[2][0] * M.M[2][0] + M.M[2][1] * M.M[2][1] + M.M[2][2] * M.M[2][2]);
			if (S2 < 1.0e-8 || M.M[3][2] < -5.0e5)
			{
				continue;
			}
			MaxS2 = FMath::Max(MaxS2, S2);
			const FVector P(M.M[3][0], M.M[3][1], M.M[3][2]);
			Lo = Lo.ComponentMin(P);
			Hi = Hi.ComponentMax(P);
		}
		if (MaxS2 <= 0.0)
		{
			return FBoxSphereBounds(LocalToWorld.GetLocation(), FVector::ZeroVector, 0.f);
		}
		const double R = (Mesh.Origin.Size() + Mesh.SphereRadius) * FMath::Sqrt(MaxS2);
		return FBoxSphereBounds(FBox(Lo - FVector(R), Hi + FVector(R)).TransformBy(LocalToWorld));
	}
};
