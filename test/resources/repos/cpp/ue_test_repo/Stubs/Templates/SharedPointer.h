// Minimal stand-ins for UE's non-UObject smart pointers.
#pragma once

template <typename T>
class TSharedPtr
{
public:
    TSharedPtr() = default;
    T* Get() const { return nullptr; }
    bool IsValid() const { return false; }
};

template <typename T>
class TSharedRef
{
public:
    T& Get() const { static T Instance; return Instance; }
};

template <typename T>
class TWeakPtr
{
public:
    TSharedPtr<T> Pin() const { return TSharedPtr<T>(); }
};

template <typename T, typename... ArgTypes>
TSharedRef<T> MakeShared(ArgTypes&&... Args)
{
    return TSharedRef<T>();
}
