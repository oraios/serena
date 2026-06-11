#include "AbilityActor.h"

void AAbilityActor::BeginPlay()
{
    AActor::BeginPlay();
    if (AbilityComponent)
    {
        AbilityComponent->TriggerAbility(FName("Dash"));
    }
}

void AAbilityActor::OnAbilityInput(const FName& AbilityName)
{
    if (AbilityComponent)
    {
        AbilityComponent->TriggerAbility(AbilityName);
    }
}
