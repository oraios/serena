// Minimal stand-ins for UE's soft (lazy-loadable) object references.
#pragma once

template <typename T>
class TSoftObjectPtr
{
public:
    TSoftObjectPtr() = default;
    T* LoadSynchronous() const { return nullptr; }
    bool IsValid() const { return false; }
};

template <typename T>
class TSoftClassPtr
{
public:
    TSoftClassPtr() = default;
};
