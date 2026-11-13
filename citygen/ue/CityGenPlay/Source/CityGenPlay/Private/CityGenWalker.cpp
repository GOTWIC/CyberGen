#include "CityGenWalker.h"

#include "Animation/AnimInstance.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/InputComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/Controller.h"
#include "GameFramework/PlayerController.h"
#include "HAL/PlatformMisc.h"
#include "InputCoreTypes.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "TimerManager.h"

DEFINE_LOG_CATEGORY_STATIC(LogCityGenWalker, Log, All);

ACityGenWalker::ACityGenWalker(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	PrimaryActorTick.bCanEverTick = true;
	GetCapsuleComponent()->InitCapsuleSize(34.f, 96.f);
	// the body turns with the view; the camera alone looks up and down
	bUseControllerRotationYaw = true;
	bUseControllerRotationPitch = false;
	bUseControllerRotationRoll = false;
	BaseEyeHeight = EyeHeightCm;

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Eyes"));
	Camera->SetupAttachment(GetCapsuleComponent());
	Camera->SetRelativeLocation(FVector(EyeForwardCm, 0.f, EyeHeightCm));
	Camera->bUsePawnControlRotation = true;
	Camera->SetFieldOfView(90.f);

	USkeletalMeshComponent* Body = GetMesh();
	Body->SetOwnerNoSee(false);           // the player sees its own body (its head hidden)
	Body->SetOnlyOwnerSee(false);
	Body->SetCastShadow(false);           // the shadow is the whole body's, below
	Body->SetRelativeLocationAndRotation(BodyOffset, BodyRotation);
	Body->SetCollisionProfileName(TEXT("CharacterMesh"));
	Body->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;

	// the body's shadow, head and all: the same mesh and animation, drawn into shadows only
	ShadowBody = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("ShadowBody"));
	ShadowBody->SetupAttachment(GetCapsuleComponent());
	ShadowBody->SetRelativeLocationAndRotation(BodyOffset, BodyRotation);
	ShadowBody->SetRenderInMainPass(false);
	ShadowBody->SetRenderInDepthPass(false);
	ShadowBody->SetCastShadow(true);
	ShadowBody->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	ShadowBody->SetGenerateOverlapEvents(false);
	ShadowBody->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;

	UCharacterMovementComponent* M = GetCharacterMovement();
	M->MaxWalkSpeed = WalkSpeedCmS;
	M->MaxStepHeight = 45.f;              // a curb (0.2 m) and a stair's step
	M->SetWalkableFloorAngle(50.f);
	M->JumpZVelocity = 450.f;
	M->AirControl = 0.3f;
	M->BrakingDecelerationWalking = 2000.f;
	M->bOrientRotationToMovement = false;
}

void ACityGenWalker::ApplyBody()
{
	for (USkeletalMeshComponent* Body : {GetMesh(), ShadowBody.Get()})
	{
		if (!Body)
		{
			continue;
		}
		if (BodyMesh && Body->GetSkeletalMeshAsset() != BodyMesh)
		{
			Body->SetSkeletalMeshAsset(BodyMesh);
		}
		if (BodyAnim)
		{
			Body->SetAnimationMode(EAnimationMode::AnimationBlueprint);
			if (Body->GetAnimClass() != BodyAnim)
			{
				Body->SetAnimInstanceClass(BodyAnim);
			}
		}
		Body->SetRelativeLocationAndRotation(BodyOffset, BodyRotation);
	}
	if (USkeletalMeshComponent* Body = GetMesh())
	{
		Body->SetOwnerNoSee(false);
		Body->SetOnlyOwnerSee(false);
	}
	BaseEyeHeight = EyeHeightCm;
	if (Camera)
	{
		Camera->SetRelativeLocation(FVector(EyeForwardCm, 0.f, EyeHeightCm));
	}
	if (UCharacterMovementComponent* M = GetCharacterMovement())
	{
		M->MaxWalkSpeed = WalkSpeedCmS;
	}
}

void ACityGenWalker::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	ApplyBody();
}

void ACityGenWalker::PostInitializeComponents()
{
	Super::PostInitializeComponents();
	ApplyBody();
}

void ACityGenWalker::SetFirstPerson(bool bOn)
{
	USkeletalMeshComponent* Body = GetMesh();
	if (!Body || !Body->GetSkeletalMeshAsset() || HiddenBone.IsNone() ||
		Body->GetBoneIndex(HiddenBone) == INDEX_NONE)
	{
		return;
	}
	// the head out of its own view (the camera sits at the eyes); seen from elsewhere (the
	// free camera) it is whole
	if (bOn)
	{
		Body->HideBoneByName(HiddenBone, PBO_None);
	}
	else
	{
		Body->UnHideBoneByName(HiddenBone);
	}
}

void ACityGenWalker::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);
	SetFirstPerson(NewController && NewController->IsLocalPlayerController());
}

void ACityGenWalker::UnPossessed()
{
	Super::UnPossessed();
	SetFirstPerson(false);
}

void ACityGenWalker::BeginPlay()
{
	Super::BeginPlay();
	SetFirstPerson(IsLocallyControlled() && IsPlayerControlled());
	const USkeletalMeshComponent* Body = GetMesh();
	const FVector L = GetActorLocation();
	UE_LOG(LogCityGenWalker, Display,
		TEXT("CITYGEN_WALKER %s: body %s, %s its player, at (%.2f, %.2f, %.2f) m"),
		*GetClass()->GetName(),
		Body && Body->GetSkeletalMeshAsset() ? *Body->GetSkeletalMeshAsset()->GetPathName() : TEXT("none"),
		HasVisibleBody() ? TEXT("seen by") : TEXT("NOT seen by"),
		L.X / 100.0, -L.Y / 100.0, L.Z / 100.0);
	// -CityGenSelfie=SECONDS (a packaged game's proof): after that long, a screenshot
	// looking down at the body and one looking ahead, then the game quits
	float After = 0.f;
	if (IsPlayerControlled() && FParse::Value(FCommandLine::Get(), TEXT("-CityGenSelfie="), After))
	{
		GetWorldTimerManager().SetTimer(SelfieTimer, this, &ACityGenWalker::SelfieStep,
			FMath::Max(After, 1.f), false);
	}
}

void ACityGenWalker::SelfieStep()
{
	APlayerController* PC = Cast<APlayerController>(GetController());
	if (!PC)
	{
		return;
	}
	static const float Pitch[] = {-68.f, -8.f};
	if (SelfieShot == 0 && !SelfieAimed)
	{
		PC->ConsoleCommand(TEXT("CityGen.Night 0"));       // (by day: the play features')
	}
	if (SelfieShot < 2)
	{
		if (SelfieAimed)
		{
			PC->ConsoleCommand(TEXT("shot"));
			const FVector L = GetActorLocation();
			UE_LOG(LogCityGenWalker, Display, TEXT("CITYGEN_WALKER selfie %d at (%.2f, %.2f, %.2f) m, %s"),
				SelfieShot, L.X / 100.0, -L.Y / 100.0, L.Z / 100.0,
				GetCharacterMovement()->IsMovingOnGround() ? TEXT("on the ground") : TEXT("NOT on the ground"));
			++SelfieShot;
			SelfieAimed = false;
		}
		else
		{
			FRotator R = PC->GetControlRotation();
			R.Pitch = Pitch[SelfieShot];
			PC->SetControlRotation(R);
			SelfieAimed = true;
		}
		GetWorldTimerManager().SetTimer(SelfieTimer, this, &ACityGenWalker::SelfieStep, 2.f, false);
		return;
	}
	UE_LOG(LogCityGenWalker, Display, TEXT("CITYGEN_WALKER selfies done"));
	FPlatformMisc::RequestExit(false, TEXT("CityGenSelfie"));
}

bool ACityGenWalker::HasVisibleBody() const
{
	const USkeletalMeshComponent* Body = GetMesh();
	return Body && Body->GetSkeletalMeshAsset() && Body->IsVisible() && !Body->bOwnerNoSee &&
		!Body->bHiddenInGame;
}

void ACityGenWalker::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	// looking down, the eyes go forward over the chest (the head stays behind them)
	if (Camera && Controller)
	{
		const float Pitch = FRotator::NormalizeAxis(float(Controller->GetControlRotation().Pitch));
		const float Down = FMath::Clamp(-FMath::Sin(FMath::DegreesToRadians(Pitch)), 0.f, 1.f);
		Camera->SetRelativeLocation(FVector(EyeForwardCm + EyeForwardDownCm * Down, 0.f,
			EyeHeightCm));
	}
}

void ACityGenWalker::SetupPlayerInputComponent(UInputComponent* Input)
{
	Super::SetupPlayerInputComponent(Input);
	if (!Input)
	{
		return;
	}
	// key bindings of the input component itself (no project input settings needed, as the
	// play features' keys)
	Input->BindAxisKey(EKeys::W, this, &ACityGenWalker::Forward);
	Input->BindAxisKey(EKeys::Up, this, &ACityGenWalker::Forward);
	Input->BindAxisKey(EKeys::S, this, &ACityGenWalker::Back);
	Input->BindAxisKey(EKeys::Down, this, &ACityGenWalker::Back);
	Input->BindAxisKey(EKeys::D, this, &ACityGenWalker::Right);
	Input->BindAxisKey(EKeys::Right, this, &ACityGenWalker::Right);
	Input->BindAxisKey(EKeys::A, this, &ACityGenWalker::Left);
	Input->BindAxisKey(EKeys::Left, this, &ACityGenWalker::Left);
	Input->BindAxisKey(EKeys::Gamepad_LeftY, this, &ACityGenWalker::StickForward);
	Input->BindAxisKey(EKeys::Gamepad_LeftX, this, &ACityGenWalker::StickRight);
	Input->BindAxisKey(EKeys::MouseX, this, &ACityGenWalker::Turn);
	Input->BindAxisKey(EKeys::MouseY, this, &ACityGenWalker::LookUp);
	Input->BindKey(EKeys::SpaceBar, IE_Pressed, this, &ACityGenWalker::StartJump);
	Input->BindKey(EKeys::SpaceBar, IE_Released, this, &ACityGenWalker::EndJump);
	Input->BindKey(EKeys::Gamepad_FaceButton_Bottom, IE_Pressed, this, &ACityGenWalker::StartJump);
	Input->BindKey(EKeys::Gamepad_FaceButton_Bottom, IE_Released, this, &ACityGenWalker::EndJump);
	Input->BindKey(EKeys::LeftShift, IE_Pressed, this, &ACityGenWalker::RunOn);
	Input->BindKey(EKeys::LeftShift, IE_Released, this, &ACityGenWalker::RunOff);
}

void ACityGenWalker::Move(const FVector& Axis, float V)
{
	if (V == 0.f || !Controller)
	{
		return;
	}
	const FRotator Yaw(0.f, Controller->GetControlRotation().Yaw, 0.f);
	AddMovementInput(Yaw.RotateVector(Axis), V);
}

void ACityGenWalker::Forward(float V) { Move(FVector::ForwardVector, V); }
void ACityGenWalker::Back(float V) { Move(FVector::ForwardVector, -V); }
void ACityGenWalker::Right(float V) { Move(FVector::RightVector, V); }
void ACityGenWalker::Left(float V) { Move(FVector::RightVector, -V); }
void ACityGenWalker::StickForward(float V) { Move(FVector::ForwardVector, V); }
void ACityGenWalker::StickRight(float V) { Move(FVector::RightVector, V); }

void ACityGenWalker::Turn(float V)
{
	if (V != 0.f)
	{
		AddControllerYawInput(V);
	}
}

void ACityGenWalker::LookUp(float V)
{
	if (V != 0.f)
	{
		AddControllerPitchInput(-V);       // the mouse forward looks up
	}
}

void ACityGenWalker::StartJump()
{
	const AController* C = GetController();
	if (C && !C->IsMoveInputIgnored())
	{
		Jump();
	}
}

void ACityGenWalker::EndJump()
{
	StopJumping();
}

void ACityGenWalker::RunOn()
{
	GetCharacterMovement()->MaxWalkSpeed = RunSpeedCmS;
}

void ACityGenWalker::RunOff()
{
	GetCharacterMovement()->MaxWalkSpeed = WalkSpeedCmS;
}
