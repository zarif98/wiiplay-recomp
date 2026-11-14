#include "runtime_product.h"

namespace RuntimeProduct {

const Descriptor& Active() noexcept {
    static constexpr Descriptor descriptor{
        Kind::BaseGame,
        "Wii Play Tanks 4P",
    };
    return descriptor;
}

} // namespace RuntimeProduct
