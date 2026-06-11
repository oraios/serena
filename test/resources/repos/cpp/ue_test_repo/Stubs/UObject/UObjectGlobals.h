// Minimal stand-ins for UObject global helpers (Cast, NewObject).
#pragma once

class UObject;

template <typename T>
T* Cast(UObject* Object)
{
    return nullptr;
}

template <typename T>
T* NewObject(UObject* Outer = nullptr)
{
    return nullptr;
}
