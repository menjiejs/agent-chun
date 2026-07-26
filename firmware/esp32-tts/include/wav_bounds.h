#pragma once

#include <stdint.h>

inline bool resolveRiffRemaining(
    uint32_t riffSize,
    int32_t responseLength,
    uint32_t& riffRemaining) {
  if (riffSize < 4) {
    return false;
  }
  riffRemaining = riffSize - 4;
  if (responseLength < 0) {
    return true;
  }

  const uint64_t declaredTotal = static_cast<uint64_t>(riffSize) + 8U;
  const uint64_t actualTotal = static_cast<uint32_t>(responseLength);
  if (actualTotal < declaredTotal) {
    return false;
  }
  if (actualTotal == declaredTotal + 4U) {
    riffRemaining += 4U;
  }
  return true;
}
