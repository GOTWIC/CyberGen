// The walking player (`citygen unreal --play walk`, the default): a character with a body the
// player sees, in first person. The importer makes BP_CityGenWalker (its body the project's
// own character's: mesh, animation and placement) and GM_CityGenWalk, the level's game mode
// override. W A S D or the arrows to walk, the mouse to look, Shift to run, Space to jump;
// the play features' `.` swaps it for the free camera and back.

#pragma once

#include "CoreMinimal.h"
#include "Engine/TimerHandle.h"
#include "GameFramework/Character.h"
#include "CityGenWalker.generated.h"

class UCameraComponent;
class UAnimInstance;
class USkeletalMesh;
class USkeletalMeshComponent;

UCLASS(Blueprintable)
class CITYGENPLAY_API ACityGenWalker : public ACharacter
{
	GENERATED_BODY()

public:
	ACityGenWalker(const FObjectInitializer& ObjectInitializer);

	/** The body (the importer sets the project's own character's). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "CityGen")
	TObjectPtr<USkeletalMesh> BodyMesh;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "CityGen")
	TSubclassOf<UAnimInstance> BodyAnim;

	/** The body's place on the capsule (the template's: its feet at the capsule's bottom,
	 *  facing x). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "CityGen")
	FVector BodyOffset = FVector(0.f, 0.f, -96.f);

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "CityGen")
	FRotator BodyRotation = FRotator(0.f, -90.f, 0.f);

	/** The eyes over the capsule's middle and forward of it (cm): with the head hidden in
	 *  the player's own view, the chest, arms and feet are in view looking down. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "CityGen")
	float EyeHeightCm = 68.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "CityGen")
	float EyeForwardCm = 9.f;

	/** How much further forward the eyes go looking straight down (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "CityGen")
	float EyeForwardDownCm = 8.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "CityGen")
	float WalkSpeedCmS = 420.f;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "CityGen")
	float RunSpeedCmS = 850.f;

	/** The bone (and what hangs off it) hidden in the player's own view: the head. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "CityGen")
	FName HiddenBone = FName(TEXT("neck_02"));

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "CityGen")
	TObjectPtr<UCameraComponent> Camera;

	/** The whole body again, drawn into shadows only (the visible one has no head). */
	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category = "CityGen")
	TObjectPtr<USkeletalMeshComponent> ShadowBody;

	/** Whether the player sees a body (a mesh drawn for its owner). */
	UFUNCTION(BlueprintCallable, Category = "CityGen")
	bool HasVisibleBody() const;

	virtual void OnConstruction(const FTransform& Transform) override;
	virtual void PostInitializeComponents() override;
	virtual void BeginPlay() override;
	virtual void PossessedBy(AController* NewController) override;
	virtual void UnPossessed() override;
	virtual void Tick(float DeltaSeconds) override;

protected:
	virtual void SetupPlayerInputComponent(UInputComponent* Input) override;

private:
	void ApplyBody();
	void SetFirstPerson(bool bOn);
	void Forward(float V);
	void Back(float V);
	void Right(float V);
	void Left(float V);
	void StickForward(float V);
	void StickRight(float V);
	void Turn(float V);
	void LookUp(float V);
	void StartJump();
	void EndJump();
	void RunOn();
	void RunOff();
	void Move(const FVector& Axis, float V);
	void SelfieStep();

	FTimerHandle SelfieTimer;
	int32 SelfieShot = 0;
	bool SelfieAimed = false;
};
