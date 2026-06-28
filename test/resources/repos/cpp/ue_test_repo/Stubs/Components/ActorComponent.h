#pragma once

#include "UObject/Object.h"

class UActorComponent : public UObject
{
public:
    virtual void BeginPlay() {}
    virtual void TickComponent(float DeltaTime) {}
};
