# 智谱 TTS 与 ESP32 播放接入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为芷春 FastAPI 增加受鉴权保护的 `/tts` WAV 接口，并提供能通过 MAX98357 流式播放该音频的 Arduino/PlatformIO ESP32 固件。

**Architecture:** Mac 端通过独立 TTS 客户端调用智谱 `glm-tts`，验证完整 WAV 后由 FastAPI 直接返回音频字节。ESP32 在同一局域网中请求 `/tts`，解析 RIFF/WAVE 数据并分块写入 I²S；智谱密钥只保留在 Mac。

**Tech Stack:** Python 3.14、FastAPI、requests、unittest、Arduino、PlatformIO、ESP32 I²S、MAX98357

## Global Constraints

- 系统仅供用户个人在家庭或个人局域网内使用。
- TTS 固定使用 `glm-tts`、`tongtong` 音色和 WAV 输出。
- `POST /tts` 直接返回 `audio/wav`，请求体为 `{"text": "..."}`。
- 文本去除首尾空白后不能为空，最大长度为 1024 个字符。
- Mac 必须先验证智谱响应为 RIFF/WAVE，再把音频返回 ESP32。
- `HOST` 默认值保持 `127.0.0.1`；局域网运行时通过 `.env` 设置 `HOST=0.0.0.0`。
- ESP32 只保存芷春服务的 `API_TOKEN`，不保存 `ZHIPU_API_KEY`。
- ESP32 以小块缓冲区流式播放，不把整段 WAV 放入内存。
- 本阶段只完成 TTS 和 MAX98357 播放，不接入 INMP441、ASR、唤醒词或自动聊天。
- 现有 `/chat` 与 `/ws/chat` 格式保持不变。

---

### Task 1: 智谱 TTS 客户端

**Files:**
- Create: `app/tts_client.py`
- Create: `tests/test_tts_client.py`

**Interfaces:**
- Consumes: 环境变量 `ZHIPU_API_KEY`、`requests.post`
- Produces: `synthesize_speech(text: str, request_id: str) -> bytes`
- Produces: `TTSConfigurationError`、`TTSUnavailableError`、`TTSUpstreamError`

- [ ] **Step 1: 写失败测试**

Create `tests/test_tts_client.py`:

```python
import os
import unittest
from unittest.mock import Mock, patch

import requests

from app.tts_client import (
    TTSConfigurationError,
    TTSUnavailableError,
    TTSUpstreamError,
    synthesize_speech,
)


WAV_BYTES = b"RIFF" + (36).to_bytes(4, "little") + b"WAVE" + b"\x00" * 36


class TTSClientTest(unittest.TestCase):
    def test_requires_api_key(self):
        with patch.dict(os.environ, {"ZHIPU_API_KEY": ""}):
            with self.assertRaises(TTSConfigurationError):
                synthesize_speech("你好", "request-1")

    @patch("app.tts_client.requests.post")
    def test_returns_valid_wav(self, post):
        response = Mock(status_code=200, content=WAV_BYTES)
        post.return_value = response

        with patch.dict(os.environ, {"ZHIPU_API_KEY": "secret-key"}):
            result = synthesize_speech("你好", "request-1")

        self.assertEqual(result, WAV_BYTES)
        post.assert_called_once_with(
            "https://open.bigmodel.cn/api/paas/v4/audio/speech",
            headers={
                "Authorization": "Bearer secret-key",
                "Content-Type": "application/json",
                "X-Request-ID": "request-1",
            },
            json={
                "model": "glm-tts",
                "input": "你好",
                "voice": "tongtong",
                "response_format": "wav",
            },
            timeout=(5, 120),
        )

    @patch("app.tts_client.requests.post")
    def test_rejects_non_wav_success(self, post):
        post.return_value = Mock(status_code=200, content=b'{"error":"bad"}')

        with patch.dict(os.environ, {"ZHIPU_API_KEY": "secret-key"}):
            with self.assertRaises(TTSUpstreamError):
                synthesize_speech("你好", "request-1")

    @patch("app.tts_client.requests.post")
    def test_maps_rate_limit_to_unavailable(self, post):
        post.return_value = Mock(status_code=429, content=b"rate limited")

        with patch.dict(os.environ, {"ZHIPU_API_KEY": "secret-key"}):
            with self.assertRaises(TTSUnavailableError):
                synthesize_speech("你好", "request-1")

    @patch("app.tts_client.requests.post")
    def test_maps_timeout_to_unavailable(self, post):
        post.side_effect = requests.Timeout("private upstream detail")

        with patch.dict(os.environ, {"ZHIPU_API_KEY": "secret-key"}):
            with self.assertRaises(TTSUnavailableError):
                synthesize_speech("你好", "request-1")

    @patch("app.tts_client.requests.post")
    def test_log_excludes_text_and_key(self, post):
        private_text = "不得写入日志的语音文本"
        post.return_value = Mock(status_code=200, content=WAV_BYTES)

        with self.assertLogs("agent.server", level="INFO") as captured:
            with patch.dict(os.environ, {"ZHIPU_API_KEY": "secret-key"}):
                synthesize_speech(private_text, "request-1")

        output = "\n".join(captured.output)
        self.assertNotIn(private_text, output)
        self.assertNotIn("secret-key", output)
        self.assertIn("text_length=11", output)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
venv/bin/python -m unittest tests.test_tts_client -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app.tts_client'`.

- [ ] **Step 3: 实现最小 TTS 客户端**

Create `app/tts_client.py`:

```python
import os
import time

import requests

from app.logging_config import logger


TTS_URL = "https://open.bigmodel.cn/api/paas/v4/audio/speech"
TTS_MODEL = "glm-tts"
TTS_VOICE = "tongtong"
TTS_TIMEOUT = (5, 120)


class TTSConfigurationError(RuntimeError):
    pass


class TTSUnavailableError(RuntimeError):
    pass


class TTSUpstreamError(RuntimeError):
    pass


def is_wav(data):
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def synthesize_speech(text: str, request_id: str) -> bytes:
    api_key = os.getenv("ZHIPU_API_KEY", "").strip()
    if not api_key:
        raise TTSConfigurationError("ZHIPU_API_KEY is not configured")

    started_at = time.perf_counter()
    try:
        response = requests.post(
            TTS_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-Request-ID": request_id,
            },
            json={
                "model": TTS_MODEL,
                "input": text,
                "voice": TTS_VOICE,
                "response_format": "wav",
            },
            timeout=TTS_TIMEOUT,
        )
    except requests.Timeout as exc:
        logger.warning(
            "tts_upstream_error request_id=%s text_length=%s error_type=Timeout",
            request_id,
            len(text),
        )
        raise TTSUnavailableError("TTS request timed out") from exc
    except requests.RequestException as exc:
        logger.warning(
            "tts_upstream_error request_id=%s text_length=%s error_type=%s",
            request_id,
            len(text),
            type(exc).__name__,
        )
        raise TTSUnavailableError("TTS request failed") from exc

    logger.info(
        "tts_upstream_complete request_id=%s status_code=%s text_length=%s "
        "audio_bytes=%s duration_ms=%.2f",
        request_id,
        response.status_code,
        len(text),
        len(response.content),
        (time.perf_counter() - started_at) * 1000,
    )
    if response.status_code == 429:
        raise TTSUnavailableError("TTS is temporarily unavailable")
    if response.status_code != 200:
        raise TTSUpstreamError("TTS upstream returned an error")
    if not is_wav(response.content):
        raise TTSUpstreamError("TTS upstream returned non-WAV content")
    return response.content
```

- [ ] **Step 4: 运行客户端测试**

Run:

```bash
venv/bin/python -m unittest tests.test_tts_client -v
```

Expected: 6 tests PASS.

- [ ] **Step 5: 提交客户端**

```bash
git add app/tts_client.py tests/test_tts_client.py
git commit -m "添加智谱 TTS 客户端"
```

---

### Task 2: FastAPI `/tts` 接口与局域网监听

**Files:**
- Modify: `app/server.py`
- Modify: `tests/test_server.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `synthesize_speech(text: str, request_id: str) -> bytes`
- Produces: `POST /tts`，成功响应 `audio/wav`
- Produces: `get_host() -> str`

- [ ] **Step 1: 为验证、鉴权、成功响应和错误映射写失败测试**

Add to `tests/test_server.py`:

```python
    def test_tts_requires_authorization(self):
        response = self.client.post("/tts", json={"text": "你好"})
        self.assertEqual(response.status_code, 401)

    def test_tts_rejects_blank_text(self):
        response = self.client.post(
            "/tts",
            headers=self.headers,
            json={"text": "   "},
        )
        self.assertEqual(response.status_code, 422)

    def test_tts_rejects_text_over_1024_characters(self):
        response = self.client.post(
            "/tts",
            headers=self.headers,
            json={"text": "春" * 1025},
        )
        self.assertEqual(response.status_code, 422)

    def test_tts_returns_wav(self):
        wav = b"RIFF" + (36).to_bytes(4, "little") + b"WAVE" + b"\x00" * 36
        with patch("app.server.synthesize_speech", return_value=wav):
            response = self.client.post(
                "/tts",
                headers=self.headers,
                json={"text": " 你好 "},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/wav")
        self.assertEqual(int(response.headers["content-length"]), len(wav))
        self.assertEqual(response.content, wav)

    def test_tts_configuration_error_is_safe(self):
        with patch(
            "app.server.synthesize_speech",
            side_effect=TTSConfigurationError("private detail"),
        ):
            response = self.client.post(
                "/tts",
                headers=self.headers,
                json={"text": "你好"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private detail", response.text)

    def test_tts_upstream_error_is_safe(self):
        with patch(
            "app.server.synthesize_speech",
            side_effect=TTSUpstreamError("private detail"),
        ):
            response = self.client.post(
                "/tts",
                headers=self.headers,
                json={"text": "你好"},
            )

        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private detail", response.text)

    def test_tts_log_excludes_text_and_token(self):
        private_text = "不得写入日志的语音文本"
        wav = b"RIFF" + (36).to_bytes(4, "little") + b"WAVE" + b"\x00" * 36
        with self.assertLogs("agent.server", level="INFO") as captured:
            with patch("app.server.synthesize_speech", return_value=wav):
                self.client.post(
                    "/tts",
                    headers=self.headers,
                    json={"text": private_text},
                )

        output = "\n".join(captured.output)
        self.assertNotIn(private_text, output)
        self.assertNotIn("test-token", output)

    def test_get_host_defaults_to_loopback(self):
        with patch.dict(os.environ, {"HOST": ""}):
            self.assertEqual(get_host(), "127.0.0.1")

    def test_get_host_accepts_lan_binding(self):
        with patch.dict(os.environ, {"HOST": "0.0.0.0"}):
            self.assertEqual(get_host(), "0.0.0.0")
```

Update test imports:

```python
from app.server import app, get_host, run_server
from app.tts_client import TTSConfigurationError, TTSUpstreamError
```

Update `test_run_server_disables_unsafe_uvicorn_request_logs` so it patches `app.server.get_host` to return `127.0.0.1`.

- [ ] **Step 2: 运行接口测试确认失败**

Run:

```bash
venv/bin/python -m unittest tests.test_server -v
```

Expected: FAIL because `/tts`, `get_host` and TTS imports are not wired into `app.server`.

- [ ] **Step 3: 实现请求模型、接口与错误映射**

In `app/server.py`, import:

```python
from starlette.responses import JSONResponse, Response

from app.tts_client import (
    TTSConfigurationError,
    TTSUnavailableError,
    TTSUpstreamError,
    synthesize_speech,
)
```

Replace the fixed host constant with:

```python
HTTP_PORT = 8000


def get_host():
    return os.getenv("HOST", "").strip() or "127.0.0.1"
```

Add the request model:

```python
class TTSRequest(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def text_must_be_valid(cls, value):
        normalized = value.strip()
        if not normalized:
            raise ValueError("text must be a non-empty string")
        if len(normalized) > 1024:
            raise ValueError("text must not exceed 1024 characters")
        return normalized
```

Add the endpoint after `/chat`:

```python
@app.post("/tts", dependencies=[Depends(require_api_token)])
async def tts(request: TTSRequest, http_request: Request):
    request_id = get_request_id(http_request)
    try:
        audio = await run_in_threadpool(
            synthesize_speech,
            request.text,
            request_id,
        )
    except (TTSConfigurationError, TTSUnavailableError):
        raise HTTPException(status_code=503, detail="TTS unavailable") from None
    except TTSUpstreamError:
        raise HTTPException(status_code=502, detail="TTS upstream error") from None

    return Response(
        content=audio,
        media_type="audio/wav",
        headers={"Content-Disposition": 'inline; filename="speech.wav"'},
    )
```

Update `run_server()`:

```python
def run_server():
    host = get_host()
    print(f"HTTP 服务已启动: http://{host}:{HTTP_PORT}")
    print(f"接口文档: http://{host}:{HTTP_PORT}/docs")
    print(f"健康检查: http://{host}:{HTTP_PORT}/health")
    print(f"技能列表: http://{host}:{HTTP_PORT}/skills")
    print(f"聊天接口: http://{host}:{HTTP_PORT}/chat")
    print(f"TTS 接口: http://{host}:{HTTP_PORT}/tts")
    print(f"WebSocket 流式聊天: ws://{host}:{HTTP_PORT}/ws/chat")
    uvicorn.run(
        app,
        host=host,
        port=HTTP_PORT,
        access_log=False,
        log_level="warning",
    )
```

- [ ] **Step 4: 记录局域网配置**

Add to `.env.example`:

```env
HOST=127.0.0.1
```

- [ ] **Step 5: 运行全部 Python 测试**

Run:

```bash
venv/bin/python -m unittest discover -s tests -v
```

Expected: all existing and new tests PASS.

- [ ] **Step 6: 提交接口**

```bash
git add app/server.py tests/test_server.py .env.example
git commit -m "添加局域网 TTS 接口"
```

---

### Task 3: ESP32/PlatformIO MAX98357 播放固件

**Files:**
- Create: `firmware/esp32-tts/platformio.ini`
- Create: `firmware/esp32-tts/include/device_config.h`
- Create: `firmware/esp32-tts/include/secrets.example.h`
- Create: `firmware/esp32-tts/src/main.cpp`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: Mac 局域网 IPv4 上的 `POST /tts`、`API_TOKEN`
- Produces: ESP32 I²S PCM 输出到 MAX98357

- [ ] **Step 1: 创建双目标 PlatformIO 配置**

Create `firmware/esp32-tts/platformio.ini`:

```ini
[platformio]
default_envs = esp32dev

[env]
platform = espressif32@6.8.1
framework = arduino
monitor_speed = 115200
lib_deps =
    bblanchon/ArduinoJson@^7.0.4

[env:esp32dev]
board = esp32dev
build_flags =
    -DI2S_BCLK_PIN=26
    -DI2S_WS_PIN=25
    -DI2S_DOUT_PIN=22

[env:esp32-s3-devkitc-1]
board = esp32-s3-devkitc-1
build_flags =
    -DI2S_BCLK_PIN=16
    -DI2S_WS_PIN=17
    -DI2S_DOUT_PIN=18
```

These GPIO values define the wire mapping to use for each supported development-board target. They are centralized build settings, not assumptions hidden in playback code.

- [ ] **Step 2: 创建设备与本地密钥配置**

Create `firmware/esp32-tts/include/device_config.h`:

```cpp
#pragma once

#define TTS_TEXT "你好，BOSS，我是芷春。智谱语音已经连接成功。"
#define HTTP_TIMEOUT_MS 130000
#define AUDIO_BUFFER_SIZE 1024
```

Create `firmware/esp32-tts/include/secrets.example.h`:

```cpp
#pragma once

#define WIFI_SSID ""
#define WIFI_PASSWORD ""
#define TTS_SERVER_URL ""
#define SERVICE_API_TOKEN ""
```

Add to `.gitignore`:

```gitignore
firmware/esp32-tts/.pio/
firmware/esp32-tts/include/secrets.h
```

The user copies `secrets.example.h` to ignored `secrets.h` and fills the local Wi-Fi name, password, Mac `/tts` URL, and service `API_TOKEN`.

- [ ] **Step 3: 实现 WAV 解析与 I²S 流式播放**

Create `firmware/esp32-tts/src/main.cpp` with these complete responsibilities:

```cpp
#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <driver/i2s.h>

#include "device_config.h"
#include "secrets.h"

static const i2s_port_t I2S_PORT = I2S_NUM_0;

uint16_t readLe16(const uint8_t* data) {
  return static_cast<uint16_t>(data[0]) |
         (static_cast<uint16_t>(data[1]) << 8);
}

uint32_t readLe32(const uint8_t* data) {
  return static_cast<uint32_t>(data[0]) |
         (static_cast<uint32_t>(data[1]) << 8) |
         (static_cast<uint32_t>(data[2]) << 16) |
         (static_cast<uint32_t>(data[3]) << 24);
}

bool readExact(Stream& stream, uint8_t* buffer, size_t length) {
  size_t received = 0;
  while (received < length) {
    int count = stream.readBytes(
        reinterpret_cast<char*>(buffer + received),
        length - received);
    if (count <= 0) {
      return false;
    }
    received += static_cast<size_t>(count);
  }
  return true;
}

bool skipBytes(Stream& stream, uint32_t length) {
  uint8_t scratch[64];
  while (length > 0) {
    size_t chunk = min(static_cast<uint32_t>(sizeof(scratch)), length);
    if (!readExact(stream, scratch, chunk)) {
      return false;
    }
    length -= chunk;
  }
  return true;
}

bool configureI2S(uint32_t sampleRate) {
  i2s_config_t config = {};
  config.mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_TX);
  config.sample_rate = sampleRate;
  config.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  config.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;
  config.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  config.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  config.dma_buf_count = 8;
  config.dma_buf_len = 256;
  config.use_apll = false;
  config.tx_desc_auto_clear = true;
  config.fixed_mclk = 0;

  i2s_pin_config_t pins = {};
  pins.bck_io_num = I2S_BCLK_PIN;
  pins.ws_io_num = I2S_WS_PIN;
  pins.data_out_num = I2S_DOUT_PIN;
  pins.data_in_num = I2S_PIN_NO_CHANGE;

  i2s_driver_uninstall(I2S_PORT);
  if (i2s_driver_install(I2S_PORT, &config, 0, nullptr) != ESP_OK) {
    return false;
  }
  if (i2s_set_pin(I2S_PORT, &pins) != ESP_OK) {
    return false;
  }
  return i2s_set_clk(
             I2S_PORT,
             sampleRate,
             I2S_BITS_PER_SAMPLE_16BIT,
             I2S_CHANNEL_MONO) == ESP_OK;
}

bool findPcmData(
    Stream& stream,
    uint32_t& sampleRate,
    uint32_t& dataLength) {
  uint8_t riff[12];
  if (!readExact(stream, riff, sizeof(riff))) {
    return false;
  }
  if (memcmp(riff, "RIFF", 4) != 0 || memcmp(riff + 8, "WAVE", 4) != 0) {
    return false;
  }

  bool validFormat = false;
  while (true) {
    uint8_t header[8];
    if (!readExact(stream, header, sizeof(header))) {
      return false;
    }
    uint32_t chunkSize = readLe32(header + 4);

    if (memcmp(header, "fmt ", 4) == 0) {
      if (chunkSize < 16) {
        return false;
      }
      uint8_t format[16];
      if (!readExact(stream, format, sizeof(format))) {
        return false;
      }
      uint16_t audioFormat = readLe16(format);
      uint16_t channels = readLe16(format + 2);
      sampleRate = readLe32(format + 4);
      uint16_t bitsPerSample = readLe16(format + 14);
      if (!skipBytes(stream, chunkSize - 16)) {
        return false;
      }
      if ((chunkSize & 1U) && !skipBytes(stream, 1)) {
        return false;
      }
      validFormat =
          audioFormat == 1 && channels == 1 && bitsPerSample == 16;
      continue;
    }

    if (memcmp(header, "data", 4) == 0) {
      if (!validFormat || sampleRate != 24000) {
        return false;
      }
      dataLength = chunkSize;
      return true;
    }

    uint32_t paddedSize = chunkSize + (chunkSize & 1U);
    if (!skipBytes(stream, paddedSize)) {
      return false;
    }
  }
}

bool playTts(const char* text) {
  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);
  if (!http.begin(TTS_SERVER_URL)) {
    Serial.println("无法连接 TTS 地址");
    return false;
  }

  http.addHeader("Authorization", String("Bearer ") + SERVICE_API_TOKEN);
  http.addHeader("Content-Type", "application/json");

  JsonDocument request;
  request["text"] = text;
  String body;
  serializeJson(request, body);

  int status = http.POST(body);
  if (status != HTTP_CODE_OK) {
    Serial.printf("TTS 请求失败，HTTP %d\n", status);
    http.end();
    return false;
  }
  String contentType = http.header("Content-Type");
  if (!contentType.startsWith("audio/wav")) {
    Serial.printf("响应不是 WAV：%s\n", contentType.c_str());
    http.end();
    return false;
  }

  WiFiClient* stream = http.getStreamPtr();
  stream->setTimeout(HTTP_TIMEOUT_MS);
  uint32_t sampleRate = 0;
  uint32_t dataLength = 0;
  if (!findPcmData(*stream, sampleRate, dataLength)) {
    Serial.println("WAV 格式不受支持");
    http.end();
    return false;
  }
  if (!configureI2S(sampleRate)) {
    Serial.println("I2S 初始化失败");
    http.end();
    return false;
  }

  uint8_t buffer[AUDIO_BUFFER_SIZE];
  uint32_t remaining = dataLength;
  while (remaining > 0) {
    size_t wanted = min(
        static_cast<uint32_t>(sizeof(buffer)),
        remaining);
    int received = stream->readBytes(
        reinterpret_cast<char*>(buffer),
        wanted);
    if (received <= 0) {
      Serial.println("音频流提前中断");
      http.end();
      return false;
    }
    size_t written = 0;
    if (i2s_write(
            I2S_PORT,
            buffer,
            static_cast<size_t>(received),
            &written,
            portMAX_DELAY) != ESP_OK ||
        written != static_cast<size_t>(received)) {
      Serial.println("I2S 写入失败");
      http.end();
      return false;
    }
    remaining -= static_cast<uint32_t>(received);
  }

  i2s_wait_tx_done(I2S_PORT, portMAX_DELAY);
  i2s_zero_dma_buffer(I2S_PORT);
  http.end();
  Serial.println("播放完成");
  return true;
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("连接 Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\n已连接，IP：%s\n", WiFi.localIP().toString().c_str());
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  if (strlen(WIFI_SSID) == 0 ||
      strlen(TTS_SERVER_URL) == 0 ||
      strlen(SERVICE_API_TOKEN) == 0) {
    Serial.println("请先填写 include/secrets.h");
    return;
  }
  connectWiFi();
  playTts(TTS_TEXT);
}

void loop() {
  delay(1000);
}
```

- [ ] **Step 4: 安装 PlatformIO 并编译两个目标**

Run:

```bash
venv/bin/pip install platformio
cp firmware/esp32-tts/include/secrets.example.h firmware/esp32-tts/include/secrets.h
venv/bin/pio run -d firmware/esp32-tts -e esp32dev
venv/bin/pio run -d firmware/esp32-tts -e esp32-s3-devkitc-1
```

Expected: both environments end with `SUCCESS`. The copied `secrets.h` contains empty values but is sufficient for compile verification and remains ignored.

- [ ] **Step 5: 验证固件密钥文件被忽略**

Run:

```bash
git check-ignore -v firmware/esp32-tts/include/secrets.h
git status --short
```

Expected: `secrets.h` and `.pio/` are ignored; only intended source files appear.

- [ ] **Step 6: 提交固件**

```bash
git add .gitignore firmware/esp32-tts
git commit -m "添加 ESP32 TTS 播放固件"
```

---

### Task 4: 运行说明与端到端验收

**Files:**
- Modify: `README.md`
- Create: `docs/runbooks/zhipu-tts-esp32.md`

**Interfaces:**
- Consumes: 已实现的 `/tts`、ESP32 固件和 MAX98357 接线
- Produces: 可重复执行的启动、配置、烧录与排错流程

- [ ] **Step 1: 更新服务说明**

Update `README.md` to document:

```text
POST /tts
Authorization: Bearer 本机配置的服务访问密码
Content-Type: application/json

{"text":"你好，我是芷春"}
```

Document that the success response is `audio/wav`, and add `HOST=0.0.0.0` to the local-network configuration example.

- [ ] **Step 2: 写 ESP32 运行手册**

Create `docs/runbooks/zhipu-tts-esp32.md` with these exact operational facts:

- Mac and ESP32 must use the same Wi-Fi.
- `HOST=0.0.0.0` is required in the Mac `.env`.
- Determine the Mac LAN IPv4 with `ipconfig getifaddr en0`.
- Copy `secrets.example.h` to ignored `secrets.h`.
- Set `TTS_SERVER_URL` to the Mac LAN IPv4 plus port and path, for example `http://192.168.1.20:8000/tts`.
- Set `SERVICE_API_TOKEN` to the same value as the Mac `.env` `API_TOKEN`.
- For `esp32dev`, wire BCLK GPIO26, LRC/WS GPIO25, DIN GPIO22.
- For `esp32-s3-devkitc-1`, wire BCLK GPIO16, LRC/WS GPIO17, DIN GPIO18.
- MAX98357 VIN connects to 5V, GND to common ground, and the speaker connects only between SPK+ and SPK-.
- Build and upload with the matching PlatformIO environment.
- Use serial monitor at 115200 baud.
- Do not expose port 8000 through router port forwarding.

- [ ] **Step 3: 运行完整回归和构建**

Run:

```bash
venv/bin/python -m unittest discover -s tests -v
venv/bin/pio run -d firmware/esp32-tts -e esp32dev
venv/bin/pio run -d firmware/esp32-tts -e esp32-s3-devkitc-1
git diff --check
```

Expected: all Python tests PASS, both firmware builds report `SUCCESS`, and `git diff --check` exits 0.

- [ ] **Step 4: 使用真实智谱接口做一次本地 WAV 验收**

Start the service with the configured `.env`, then run:

```bash
set -a
source .env
set +a
curl --fail \
  --request POST \
  http://127.0.0.1:8000/tts \
  --header "Authorization: Bearer $API_TOKEN" \
  --header "Content-Type: application/json" \
  --data '{"text":"你好，BOSS，我是芷春。ESP32 语音接口已经准备好了。"}' \
  --output outputs/esp32-tts-acceptance.wav
file outputs/esp32-tts-acceptance.wav
afinfo outputs/esp32-tts-acceptance.wav
```

Expected: curl returns HTTP 200; `file` identifies RIFF/WAVE PCM; `afinfo` reports 24 kHz, 16-bit, mono audio.

- [ ] **Step 5: 提交文档**

```bash
git add README.md docs/runbooks/zhipu-tts-esp32.md
git commit -m "记录 ESP32 TTS 使用方法"
```

- [ ] **Step 6: 硬件验收**

After the exact board target is selected and connected:

```bash
venv/bin/pio device list
venv/bin/pio run -d firmware/esp32-tts -e esp32dev -t upload
venv/bin/pio device monitor -b 115200
```

For an ESP32-S3 DevKitC-1, replace `esp32dev` with `esp32-s3-devkitc-1`.

Expected serial sequence: Wi-Fi connected, TTS HTTP 200, supported WAV parsed, `播放完成`. Repeat reset three times; all three playbacks complete without truncation or persistent noise.
