#include "common.hlsl"

RWTexture2D<float4> OutputTexture : register(u0);
Texture2D<float4> InputTexture : register(t0);

cbuffer ComputeParams : register(b0)
{
    uint2 TextureSize;
    float BlurRadius;
    float _Pad;
};

[numthreads(8, 8, 1)]
void CSMain(uint3 id : SV_DispatchThreadID)
{
    if (id.x >= TextureSize.x || id.y >= TextureSize.y)
        return;

    float4 color = InputTexture[id.xy];
    float3 remapped = float3(
        Remap(color.r, 0.0, 1.0, 0.2, 0.8),
        Remap(color.g, 0.0, 1.0, 0.2, 0.8),
        Remap(color.b, 0.0, 1.0, 0.2, 0.8)
    );
    OutputTexture[id.xy] = float4(remapped, color.a);
}
