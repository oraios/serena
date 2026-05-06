module;

#include <cstdint>

module b;

auto
add(auto x, auto y) -> decltype(x + y)
{
    return x + y;
}

auto
add_f32(float x, float y) -> float
{
    return add(x, y);
}
