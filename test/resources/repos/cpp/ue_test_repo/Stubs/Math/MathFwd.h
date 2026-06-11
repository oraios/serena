// Minimal stand-ins for UE math types.
#pragma once

struct FVector
{
    double X = 0.0;
    double Y = 0.0;
    double Z = 0.0;

    FVector() = default;
    FVector(double InX, double InY, double InZ) : X(InX), Y(InY), Z(InZ) {}
};

struct FRotator
{
    double Pitch = 0.0;
    double Yaw = 0.0;
    double Roll = 0.0;
};

struct FTransform
{
    FVector GetLocation() const { return FVector(); }
    FRotator Rotator() const { return FRotator(); }
};
