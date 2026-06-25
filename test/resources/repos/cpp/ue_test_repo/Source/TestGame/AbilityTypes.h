#pragma once

#include "CoreMinimal.h"
#include "AbilityTypes.generated.h"

UENUM(BlueprintType)
enum class EAbilityState : uint8
{
    Idle,
    Active UMETA(DisplayName = "Active (in use)"),
    Cooldown,
};

USTRUCT(BlueprintType)
struct TESTGAME_API FAbilityInfo
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    FName AbilityName;

    UPROPERTY(EditAnywhere, BlueprintReadWrite)
    float CooldownSeconds = 1.0f;
};
