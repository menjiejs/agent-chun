#include <assert.h>
#include <stdint.h>

#include "wav_bounds.h"

int main() {
  const uint32_t actualResponseLength = 354960;
  const uint32_t declaredRiffSize = 354948;
  uint32_t riffRemaining = 0;

  assert(resolveRiffRemaining(
      declaredRiffSize, actualResponseLength, riffRemaining));
  assert(riffRemaining == actualResponseLength - 12);

  assert(resolveRiffRemaining(100, 108, riffRemaining));
  assert(riffRemaining == 96);

  assert(!resolveRiffRemaining(100, 107, riffRemaining));

  assert(resolveRiffRemaining(100, 116, riffRemaining));
  assert(riffRemaining == 96);
  return 0;
}
