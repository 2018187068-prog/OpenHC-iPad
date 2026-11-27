#ifndef OPENHC_FE35_BRIDGE_BOUNDS_H
#define OPENHC_FE35_BRIDGE_BOUNDS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

static inline bool fe35_bridge_checked_length(int32_t length, size_t capacity, size_t *result) {
    if (!result || length < 0 || (uintmax_t)length > (uintmax_t)capacity) return false;
    *result = (size_t)length;
    return true;
}

#endif
