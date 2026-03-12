#ifndef LIGHTING_HLSL
#define LIGHTING_HLSL

#include "common.hlsl"

cbuffer LightingConstants : register(b0)
{
    float4x4 ViewProjection;
    float3 LightDirection;
    float LightIntensity;
    float3 AmbientColor;
    float _Padding;
};

float3 CalculateDiffuse(float3 normal, float3 lightDir, float3 albedo)
{
    float ndotl = max(dot(normal, -lightDir), 0.0);
    return albedo * ndotl;
}

float3 CalculateSpecular(float3 normal, float3 lightDir, float3 viewDir, float shininess)
{
    float3 halfVec = SafeNormalize(-lightDir + viewDir);
    float ndoth = max(dot(normal, halfVec), 0.0);
    return pow(ndoth, shininess);
}

VertexOutput TransformVertex(VertexInput input)
{
    VertexOutput output;
    output.clipPos = mul(ViewProjection, float4(input.position, 1.0));
    output.worldNormal = input.normal;
    output.uv = input.uv;
    return output;
}

#endif // LIGHTING_HLSL
