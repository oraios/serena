// Minimal TObjectPtr stand-in (UE5's idiomatic UPROPERTY pointer wrapper).
#pragma once

template <typename T>
class TObjectPtr
{
public:
    TObjectPtr() = default;
    TObjectPtr(T* InPtr) {}
    T* Get() const { return nullptr; }
    T* operator->() const { return nullptr; }
    explicit operator bool() const { return false; }
};
