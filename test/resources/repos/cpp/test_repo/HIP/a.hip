// -*- mode: C -*-

#include <hip/hip_runtime.h>

__global__
void add_vectors(const float* A, const float* B, float* C)
{
    auto const idx = blockIdx.x * blockDim.x + threadIdx.x;
    C[idx] = A[idx] + B[idx];
}
