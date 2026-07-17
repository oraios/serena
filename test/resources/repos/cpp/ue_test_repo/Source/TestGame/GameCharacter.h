#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "AbilityComponent.h"
#include "Damageable.h"
#include "GameCharacter.generated.h"

UCLASS(Blueprintable)
class TESTGAME_API AGameCharacter : public ACharacter, public IDamageable
{
    GENERATED_BODY()

public:
    AGameCharacter();

    virtual void ReceiveDamage(float Amount) override;

    UFUNCTION(BlueprintCallable, Category = "Health")
    void Heal(UPARAM(ref) float& Amount);

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Spawn")
    FVector SpawnOffset = FVector(0.0, 0.0, 100.0);

    UPROPERTY(EditAnywhere, Category = "Abilities")
    TObjectPtr<UAbilityComponent> Abilities;

    UPROPERTY(VisibleAnywhere, Category = "Targeting")
    TWeakObjectPtr<AActor> CurrentTarget;

    UPROPERTY(EditAnywhere, Category = "Loadout")
    TSoftObjectPtr<UAbilityComponent> FallbackLoadout;

private:
    // Non-reflected runtime state: smart pointers and optionals are not UPROPERTYs.
    TSharedPtr<FAbilityInfo> PendingAbility;
    TOptional<float> LastDamageAmount;
    float Health = 100.0f;
};
