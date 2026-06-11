#pragma once

#include "UObject/Object.h"

class UWorld;

class AActor : public UObject
{
public:
    virtual void BeginPlay() {}
    virtual void Tick(float DeltaSeconds) {}
    UWorld* GetWorld() const { return nullptr; }
};
