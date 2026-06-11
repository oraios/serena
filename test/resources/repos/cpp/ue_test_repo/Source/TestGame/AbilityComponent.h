#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "AbilityTypes.h"
#include "AbilityComponent.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnAbilityTriggered, const FName&, AbilityName);
DECLARE_MULTICAST_DELEGATE_OneParam(FOnCooldownExpired, const FName&);

UCLASS(ClassGroup = (Custom), meta = (BlueprintSpawnableComponent))
class TESTGAME_API UAbilityComponent : public UActorComponent
{
    GENERATED_BODY()

public:
    UFUNCTION(BlueprintCallable, Category = "Abilities")
    void TriggerAbility(const FName& AbilityName);

    UFUNCTION(BlueprintPure, Category = "Abilities")
    float GetRemainingCooldown(const FName& AbilityName) const;

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Abilities")
    TArray<FAbilityInfo> Abilities;

    UPROPERTY(VisibleAnywhere, Category = "Abilities")
    TMap<FName, float> ActiveCooldowns;

    UPROPERTY(BlueprintAssignable, Category = "Abilities")
    FOnAbilityTriggered OnAbilityTriggered;

    UPROPERTY(EditAnywhere, Category = "Abilities")
    EAbilityState State = EAbilityState::Idle;

    UPROPERTY(EditAnywhere, Category = "Abilities")
    TSet<FName> UnlockedAbilities;

    // Non-dynamic delegates are not reflected and cannot be UPROPERTYs.
    FOnCooldownExpired OnCooldownExpired;
};
