#ifndef TERRAIN_SDF_HLSL
#define TERRAIN_SDF_HLSL

#include "../common.hlsl"

struct SDFBrickData
{
    float3 center;
    float halfExtent;
    int resolution;
    float maxDistance;
};

float3 WorldOffset;

float SampleSDF(float3 worldPos, SDFBrickData brick)
{
    float3 localPos = worldPos - brick.center;
    float dist = length(localPos) - brick.halfExtent;
    return dist;
}

float3 CalculateGradient(float3 worldPos, SDFBrickData brick)
{
    float eps = 0.01;
    float3 gradient;
    gradient.x = SampleSDF(worldPos + float3(eps, 0, 0), brick) - SampleSDF(worldPos - float3(eps, 0, 0), brick);
    gradient.y = SampleSDF(worldPos + float3(0, eps, 0), brick) - SampleSDF(worldPos - float3(0, eps, 0), brick);
    gradient.z = SampleSDF(worldPos + float3(0, 0, eps), brick) - SampleSDF(worldPos - float3(0, 0, eps), brick);
    return SafeNormalize(gradient);
}

#endif // TERRAIN_SDF_HLSL
