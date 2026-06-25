#pragma once

#include "CoreTypes.h"

class UObject
{
public:
    virtual ~UObject() = default;

    template <typename T>
    T* CreateDefaultSubobject(const FName& SubobjectName)
    {
        return nullptr;
    }
};
