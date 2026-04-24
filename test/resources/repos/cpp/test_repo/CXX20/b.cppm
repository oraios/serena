module;

#include <cstdint>

export module b;

export auto
add(auto x, auto y) -> decltype(x + y);

export auto
add_f32(float x, float y) -> float;

auto
add_u32(std::int32_t x, std::int32_t y) -> std::int32_t {
    return x + y;
}
