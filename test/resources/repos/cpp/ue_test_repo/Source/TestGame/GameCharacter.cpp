#include "GameCharacter.h"
#include "TestGameLog.h"

AGameCharacter::AGameCharacter()
{
    Abilities = CreateDefaultSubobject<UAbilityComponent>(FName(TEXT("Abilities")));
}

void AGameCharacter::ReceiveDamage(float Amount)
{
    check(Amount >= 0.0f);
    Health -= Amount;
    LastDamageAmount = Amount;
    UE_LOG(LogTestGame, Warning, TEXT("Received %f damage"), Amount);

    if (AActor* Target = CurrentTarget.Get())
    {
        if (AGameCharacter* OtherCharacter = Cast<AGameCharacter>(Target))
        {
            OtherCharacter->Heal(Amount);
        }
    }
}

void AGameCharacter::Heal(float& Amount)
{
    Health += Amount;
    Amount = 0.0f;
}
