#ifndef COMMON_HLSL
#define COMMON_HLSL

struct VertexInput
{
    float3 position : POSITION;
    float3 normal : NORMAL;
    float2 uv : TEXCOORD0;
};

struct VertexOutput
{
    float4 clipPos : SV_POSITION;
    float3 worldNormal : TEXCOORD0;
    float2 uv : TEXCOORD1;
};

float3 SafeNormalize(float3 v)
{
    float len = length(v);
    return len > 0.0001 ? v / len : float3(0, 0, 0);
}

float Remap(float value, float fromMin, float fromMax, float toMin, float toMax)
{
    return toMin + (value - fromMin) * (toMax - toMin) / (fromMax - fromMin);
}

#endif // COMMON_HLSL
