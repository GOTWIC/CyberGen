#include "CityGenAtmosCell.h"

#include "CityGenAtmosActor.h"
#include "Components/SceneComponent.h"

ACityGenAtmosCell::ACityGenAtmosCell()
{
	PrimaryActorTick.bCanEverTick = false;
	USceneComponent* Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	Root->SetMobility(EComponentMobility::Static);
	RootComponent = Root;
	// (no primitive: World Partition streams it by its location, the cell's middle)
#if WITH_EDITORONLY_DATA
	bIsSpatiallyLoaded = true;
#endif
}

void ACityGenAtmosCell::BeginPlay()
{
	Super::BeginPlay();
	// (a cell streamed in before the controller began play is taken by the controller's own
	// BeginPlay, which looks for every cell already in)
	if (ACityGenAtmos* A = ACityGenAtmos::Find(GetWorld()))
	{
		if (A->HasActorBegunPlay())
		{
			A->RegisterCell(this);
		}
	}
}

void ACityGenAtmosCell::EndPlay(const EEndPlayReason::Type Reason)
{
	if (ACityGenAtmos* A = ACityGenAtmos::Find(GetWorld()))
	{
		A->UnregisterCell(this);
	}
	Super::EndPlay(Reason);
}
