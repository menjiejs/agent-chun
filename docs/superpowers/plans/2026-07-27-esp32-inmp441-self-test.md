# ESP32 INMP441 麦克风自检 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一个独立 PlatformIO 固件，从 INMP441 读取音频并在串口显示随声音变化的音量值和字符音量条。

**Architecture:** 新建 `firmware/esp32-mic-test`，与现有扬声器固件完全隔离。可移植的音量计算函数先通过 PlatformIO native 单元测试验证，ESP32 程序再以 I2S 主机接收模式读取左声道 32 位采样，转换成 24 位幅度后输出约 200 ms 的统计窗口。

**Tech Stack:** PlatformIO 6、Arduino ESP32、ESP-IDF legacy I2S driver、Unity native tests、C++11

## Global Constraints

- 目标开发板为经典 ESP32-D0WDQ6，PlatformIO board 为 `esp32dev`。
- 实机串口为 `/dev/cu.usbserial-110`，串口监视器波特率为 115200。
- INMP441 接线固定为 BCLK GPIO27、WS GPIO33、数据输入 GPIO32、L/R 接 GND。
- INMP441 使用 3.3V 供电，不得接 5V、VCC 或扩展板的可切换 V 电源排。
- 采样率固定为 16 kHz，读取左声道 32 位 I2S 采样槽。
- 自检固件不联网、不读取密钥、不保存或上传录音、不初始化扬声器。
- 不修改 `firmware/esp32-tts`。

---

### Task 1: 可测试的音量计算

**Files:**
- Create: `firmware/esp32-mic-test/platformio.ini`
- Create: `firmware/esp32-mic-test/include/audio_level.h`
- Create: `firmware/esp32-mic-test/test/test_audio_level/test_main.cpp`

**Interfaces:**
- Consumes: 已右移 8 位、范围为有符号 24 位的 `int32_t` PCM 样本
- Produces: `AudioLevel calculateAudioLevel(const int32_t* samples, size_t count)`
- Produces: `uint8_t audioBarLength(uint32_t peak)`

- [ ] **Step 1: 创建 PlatformIO native 测试环境和失败测试**

Create `firmware/esp32-mic-test/platformio.ini`:

```ini
[platformio]
default_envs = esp32dev

[env:native]
platform = native
test_framework = unity
build_flags =
    -std=c++11

[env:esp32dev]
platform = espressif32@6.8.1
board = esp32dev
framework = arduino
monitor_speed = 115200
build_flags =
    -DMIC_BCLK_PIN=27
    -DMIC_WS_PIN=33
    -DMIC_DATA_PIN=32
```

Create `firmware/esp32-mic-test/test/test_audio_level/test_main.cpp`:

```cpp
#include <unity.h>

#include "audio_level.h"

void test_silence_has_zero_level() {
  const int32_t samples[] = {0, 0, 0, 0};
  AudioLevel level = calculateAudioLevel(samples, 4);
  TEST_ASSERT_EQUAL_UINT32(0, level.peak);
  TEST_ASSERT_EQUAL_UINT32(0, level.meanAbsolute);
}

void test_fixed_dc_offset_is_removed() {
  const int32_t samples[] = {1000, 1000, 1000, 1000};
  AudioLevel level = calculateAudioLevel(samples, 4);
  TEST_ASSERT_EQUAL_UINT32(0, level.peak);
  TEST_ASSERT_EQUAL_UINT32(0, level.meanAbsolute);
}

void test_varying_samples_produce_level() {
  const int32_t samples[] = {-1000, 1000, -1000, 1000};
  AudioLevel level = calculateAudioLevel(samples, 4);
  TEST_ASSERT_EQUAL_UINT32(1000, level.peak);
  TEST_ASSERT_EQUAL_UINT32(1000, level.meanAbsolute);
}

void test_empty_input_is_safe() {
  AudioLevel level = calculateAudioLevel(nullptr, 0);
  TEST_ASSERT_EQUAL_UINT32(0, level.peak);
  TEST_ASSERT_EQUAL_UINT32(0, level.meanAbsolute);
}

void test_bar_length_is_bounded() {
  TEST_ASSERT_EQUAL_UINT8(0, audioBarLength(0));
  TEST_ASSERT_EQUAL_UINT8(1, audioBarLength(20000));
  TEST_ASSERT_EQUAL_UINT8(40, audioBarLength(800000));
  TEST_ASSERT_EQUAL_UINT8(40, audioBarLength(9000000));
}

int main(int argc, char** argv) {
  UNITY_BEGIN();
  RUN_TEST(test_silence_has_zero_level);
  RUN_TEST(test_fixed_dc_offset_is_removed);
  RUN_TEST(test_varying_samples_produce_level);
  RUN_TEST(test_empty_input_is_safe);
  RUN_TEST(test_bar_length_is_bounded);
  return UNITY_END();
}
```

- [ ] **Step 2: 运行测试确认因缺少头文件而失败**

Run:

```bash
cd firmware/esp32-mic-test
/Users/yyz/.platformio/penv/bin/pio test -e native
```

Expected: FAIL with `fatal error: audio_level.h: No such file or directory`.

- [ ] **Step 3: 实现最小音量计算**

Create `firmware/esp32-mic-test/include/audio_level.h`:

```cpp
#pragma once

#include <stddef.h>
#include <stdint.h>

struct AudioLevel {
  uint32_t peak;
  uint32_t meanAbsolute;
};

inline AudioLevel calculateAudioLevel(
    const int32_t* samples,
    size_t count) {
  AudioLevel result = {0, 0};
  if (samples == nullptr || count == 0) {
    return result;
  }

  int64_t sum = 0;
  for (size_t index = 0; index < count; ++index) {
    sum += samples[index];
  }
  const int32_t mean = static_cast<int32_t>(sum / count);

  uint64_t absoluteSum = 0;
  for (size_t index = 0; index < count; ++index) {
    int64_t centered = static_cast<int64_t>(samples[index]) - mean;
    uint32_t magnitude = static_cast<uint32_t>(
        centered < 0 ? -centered : centered);
    if (magnitude > result.peak) {
      result.peak = magnitude;
    }
    absoluteSum += magnitude;
  }
  result.meanAbsolute = static_cast<uint32_t>(absoluteSum / count);
  return result;
}

inline uint8_t audioBarLength(uint32_t peak) {
  const uint32_t scaled = peak / 20000U;
  return static_cast<uint8_t>(scaled > 40U ? 40U : scaled);
}
```

- [ ] **Step 4: 运行 native 测试确认通过**

Run:

```bash
cd firmware/esp32-mic-test
/Users/yyz/.platformio/penv/bin/pio test -e native
```

Expected: 5 tests PASS, 0 failures.

- [ ] **Step 5: 提交音量算法**

```bash
git add firmware/esp32-mic-test/platformio.ini \
  firmware/esp32-mic-test/include/audio_level.h \
  firmware/esp32-mic-test/test/test_audio_level/test_main.cpp
git commit -m "添加麦克风音量计算"
```

---

### Task 2: INMP441 串口自检固件

**Files:**
- Create: `firmware/esp32-mic-test/src/main.cpp`

**Interfaces:**
- Consumes: `calculateAudioLevel(...)`、`audioBarLength(...)`
- Consumes: `MIC_BCLK_PIN=27`、`MIC_WS_PIN=33`、`MIC_DATA_PIN=32`
- Produces: 115200 波特率串口的初始化状态、峰值、平均绝对幅度和字符音量条

- [ ] **Step 1: 创建最小 I2S 接收程序**

Create `firmware/esp32-mic-test/src/main.cpp`:

```cpp
#include <Arduino.h>
#include <driver/i2s.h>

#include "audio_level.h"

namespace {

const i2s_port_t kI2SPort = I2S_NUM_0;
const uint32_t kSampleRate = 16000;
const size_t kSampleCount = 256;
int32_t rawSamples[kSampleCount];
int32_t pcmSamples[kSampleCount];

bool configureMicrophone() {
  i2s_config_t config = {};
  config.mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_RX);
  config.sample_rate = kSampleRate;
  config.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;
  config.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;
  config.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  config.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  config.dma_buf_count = 8;
  config.dma_buf_len = 128;
  config.use_apll = false;
  config.tx_desc_auto_clear = false;
  config.fixed_mclk = 0;

  i2s_pin_config_t pins = {};
  pins.bck_io_num = MIC_BCLK_PIN;
  pins.ws_io_num = MIC_WS_PIN;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num = MIC_DATA_PIN;

  if (i2s_driver_install(kI2SPort, &config, 0, nullptr) != ESP_OK) {
    return false;
  }
  if (i2s_set_pin(kI2SPort, &pins) != ESP_OK) {
    i2s_driver_uninstall(kI2SPort);
    return false;
  }
  return true;
}

void printBar(uint8_t length) {
  Serial.print('[');
  for (uint8_t index = 0; index < 40; ++index) {
    Serial.print(index < length ? '#' : ' ');
  }
  Serial.print(']');
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(800);
  Serial.println();
  Serial.println("INMP441 microphone self-test");
  Serial.println("Pins: BCLK=27 WS=33 SD=32 channel=left");

  if (!configureMicrophone()) {
    Serial.println("ERROR: I2S initialization failed");
    while (true) {
      delay(1000);
    }
  }
  Serial.println("I2S ready. Speak or clap near the microphone.");
}

void loop() {
  size_t bytesRead = 0;
  esp_err_t status = i2s_read(
      kI2SPort,
      rawSamples,
      sizeof(rawSamples),
      &bytesRead,
      pdMS_TO_TICKS(1000));

  if (status != ESP_OK || bytesRead == 0) {
    Serial.printf(
        "ERROR: I2S read failed status=%d bytes=%u\n",
        static_cast<int>(status),
        static_cast<unsigned>(bytesRead));
    delay(200);
    return;
  }

  const size_t count = bytesRead / sizeof(rawSamples[0]);
  for (size_t index = 0; index < count; ++index) {
    pcmSamples[index] = rawSamples[index] >> 8;
  }

  AudioLevel level = calculateAudioLevel(pcmSamples, count);
  printBar(audioBarLength(level.peak));
  Serial.printf(
      " peak=%lu mean=%lu samples=%u\n",
      static_cast<unsigned long>(level.peak),
      static_cast<unsigned long>(level.meanAbsolute),
      static_cast<unsigned>(count));
  delay(180);
}
```

- [ ] **Step 2: 编译 ESP32 固件**

Run:

```bash
cd firmware/esp32-mic-test
/Users/yyz/.platformio/penv/bin/pio run -e esp32dev
```

Expected: `SUCCESS`, with firmware generated at
`.pio/build/esp32dev/firmware.bin`.

- [ ] **Step 3: 重新运行 native 测试防止回归**

Run:

```bash
cd firmware/esp32-mic-test
/Users/yyz/.platformio/penv/bin/pio test -e native
```

Expected: 5 tests PASS, 0 failures.

- [ ] **Step 4: 提交自检固件**

```bash
git add firmware/esp32-mic-test/src/main.cpp
git commit -m "添加 INMP441 串口自检固件"
```

---

### Task 3: 实机烧录与验收

**Files:**
- No source file changes

**Interfaces:**
- Consumes: `.pio/build/esp32dev/firmware.bin`
- Consumes: `/dev/cu.usbserial-110`
- Produces: 实机安静与说话/拍手两种情况下的串口音量证据

- [ ] **Step 1: 确认目标串口仍然存在**

Run:

```bash
test -e /dev/cu.usbserial-110
```

Expected: exit code 0.

- [ ] **Step 2: 烧录自检固件**

Run:

```bash
cd firmware/esp32-mic-test
/Users/yyz/.platformio/penv/bin/pio run -e esp32dev \
  -t upload --upload-port /dev/cu.usbserial-110
```

Expected: `SUCCESS` and device reset after upload.

- [ ] **Step 3: 打开串口并采集初始化输出**

Run:

```bash
cd firmware/esp32-mic-test
/Users/yyz/.platformio/penv/bin/pio device monitor \
  --port /dev/cu.usbserial-110 --baud 115200
```

Expected:

```text
INMP441 microphone self-test
Pins: BCLK=27 WS=33 SD=32 channel=left
I2S ready. Speak or clap near the microphone.
```

- [ ] **Step 4: 完成实机声音验收**

保持安静观察数值，然后对着麦克风说话或在附近拍手。验收条件：

- 安静时持续输出有效的 `samples`，无 `I2S read failed`。
- 说话或拍手时 `peak`、`mean` 和 `#` 数量相对安静状态明显升高。
- 连续观察约 30 秒，开发板不反复重启。

若数值始终为零，先断电后逐一核对 VDD=3V3、GND、L/R=GND、
SCK=D27/S、WS=D33/S、SD=D32/S。若数值持续接近满量程，先断电后检查
SD 是否误插到 V 孔以及 L/R 是否悬空。

