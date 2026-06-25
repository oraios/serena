#include "AbilityComponent.h"

void UAbilityComponent::TriggerAbility(const FName& AbilityName)
{
    if (!ActiveCooldowns.Contains(AbilityName))
    {
        ActiveCooldowns.Add(AbilityName, 1.0f);
    }
    State = EAbilityState::Active;
    OnAbilityTriggered.Broadcast(AbilityName);
}

float UAbilityComponent::GetRemainingCooldown(const FName& AbilityName) const
{
    return 0.0f;
}
