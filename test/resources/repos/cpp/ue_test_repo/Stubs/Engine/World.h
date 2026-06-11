#pragma once

#include "UObject/Object.h"

class UWorld : public UObject
{
public:
    float GetTimeSeconds() const { return 0.0f; }
};
