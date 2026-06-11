// Minimal TUniquePtr stand-in.
#pragma once

template <typename T>
class TUniquePtr
{
public:
    TUniquePtr() = default;
    T* Get() const { return nullptr; }
    bool IsValid() const { return false; }
};

template <typename T, typename... ArgTypes>
TUniquePtr<T> MakeUnique(ArgTypes&&... Args)
{
    return TUniquePtr<T>();
}
