#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AbilityComponent.h"
#include "AbilityActor.generated.h"

UCLASS(Blueprintable)
class TESTGAME_API AAbilityActor : public AActor
{
    GENERATED_BODY()

public:
    virtual void BeginPlay() override;

    UFUNCTION(BlueprintCallable, Category = "Input")
    void OnAbilityInput(const FName& AbilityName);

    UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Components")
    TObjectPtr<UAbilityComponent> AbilityComponent = nullptr;

    UPROPERTY(EditDefaultsOnly, Category = "Abilities")
    TSubclassOf<UAbilityComponent> ComponentClass;
};
