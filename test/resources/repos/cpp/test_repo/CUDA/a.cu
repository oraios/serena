#include <cstdio>
#include <cstdlib>

__global__ auto
cuda_hello() -> void
{
    printf("Hello World from GPU!\n");
}

auto
main() -> int
{
    cuda_hello<<<1, 1>>>();
    cudaDeviceSynchronize();
    return EXIT_SUCCESS;
}
