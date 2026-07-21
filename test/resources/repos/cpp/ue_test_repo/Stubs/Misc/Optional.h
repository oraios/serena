// Minimal TOptional stand-in.
#pragma once

template <typename T>
class TOptional
{
public:
    TOptional() = default;
    TOptional(const T& InValue) {}
    bool IsSet() const { return false; }
    const T& GetValue() const { static T Value; return Value; }
};
