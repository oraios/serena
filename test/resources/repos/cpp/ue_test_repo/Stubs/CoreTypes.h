// Minimal stand-ins for core Unreal types and ubiquitous utility macros.
// Real homes in UE: TEXT/FORCEINLINE in Misc/, assertions in Misc/AssertionMacros.h,
// UE_DEPRECATED in Misc/CoreMiscDefines.h; folded together here for stub brevity.
#pragma once

class FName
{
public:
    FName() = default;
    FName(const char* InName) {}
    bool operator==(const FName& Other) const { return true; }
    bool operator<(const FName& Other) const { return false; }
};

class FString
{
public:
    FString() = default;
    FString(const char* InStr) {}
};

class FText
{
public:
    FText() = default;
    static FText FromString(const FString& InString) { return FText(); }
};

using int32 = int;
using uint32 = unsigned int;
using uint8 = unsigned char;

#define TEXT(x) x
#define FORCEINLINE inline
#define UE_DEPRECATED(Version, Message)

#define check(expr)
#define checkf(expr, format, ...)
#define verify(expr)
#define ensure(expr) (!!(expr))
#define ensureMsgf(expr, format, ...) (!!(expr))
