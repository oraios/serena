// Minimal TWeakObjectPtr stand-in.
#pragma once

template <typename T>
class TWeakObjectPtr
{
public:
    TWeakObjectPtr() = default;
    TWeakObjectPtr(T* InPtr) {}
    T* Get() const { return nullptr; }
    bool IsValid() const { return false; }
};
