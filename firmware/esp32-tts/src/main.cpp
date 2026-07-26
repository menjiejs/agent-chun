#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <driver/i2s.h>

#include "device_config.h"
#include "secrets.h"
#include "wav_bounds.h"

static const i2s_port_t I2S_PORT = I2S_NUM_0;
static bool i2sInstalled = false;
static const uint8_t I2S_DMA_BUFFER_COUNT = 8;
static const uint16_t I2S_DMA_BUFFER_LENGTH = 256;

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
        reinterpret_cast<char*>(buffer + received), length - received);
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

void releaseI2S() {
  if (i2sInstalled) {
    i2s_zero_dma_buffer(I2S_PORT);
    i2s_driver_uninstall(I2S_PORT);
    i2sInstalled = false;
  }
}

bool configureI2S(uint32_t sampleRate) {
  releaseI2S();

  i2s_config_t config = {};
  config.mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_TX);
  config.sample_rate = sampleRate;
  config.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  config.channel_format = I2S_CHANNEL_FMT_ONLY_LEFT;
  config.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  config.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
  config.dma_buf_count = I2S_DMA_BUFFER_COUNT;
  config.dma_buf_len = I2S_DMA_BUFFER_LENGTH;
  config.use_apll = false;
  config.tx_desc_auto_clear = true;
  config.fixed_mclk = 0;

  i2s_pin_config_t pins = {};
  pins.bck_io_num = I2S_BCLK_PIN;
  pins.ws_io_num = I2S_WS_PIN;
  pins.data_out_num = I2S_DOUT_PIN;
  pins.data_in_num = I2S_PIN_NO_CHANGE;

  if (i2s_driver_install(I2S_PORT, &config, 0, nullptr) != ESP_OK) {
    return false;
  }
  i2sInstalled = true;
  if (i2s_set_pin(I2S_PORT, &pins) != ESP_OK ||
      i2s_set_clk(
          I2S_PORT,
          sampleRate,
          I2S_BITS_PER_SAMPLE_16BIT,
          I2S_CHANNEL_MONO) != ESP_OK) {
    releaseI2S();
    return false;
  }
  return true;
}

bool drainI2S(uint32_t sampleRate) {
  uint8_t silence[64] = {};
  size_t written = 0;
  if (i2s_write(
          I2S_PORT, silence, sizeof(silence), &written, portMAX_DELAY) !=
          ESP_OK ||
      written != sizeof(silence)) {
    return false;
  }
  uint32_t drainDelayMs =
      (static_cast<uint32_t>(I2S_DMA_BUFFER_COUNT) *
           I2S_DMA_BUFFER_LENGTH * 1000U +
       sampleRate - 1U) /
      sampleRate;
  delay(drainDelayMs);
  i2s_zero_dma_buffer(I2S_PORT);
  return true;
}

bool findPcmData(
    Stream& stream,
    int32_t responseLength,
    uint32_t& sampleRate,
    uint32_t& dataLength) {
  uint8_t riff[12];
  if (!readExact(stream, riff, sizeof(riff))) {
    return false;
  }
  if (memcmp(riff, "RIFF", 4) != 0 || memcmp(riff + 8, "WAVE", 4) != 0) {
    return false;
  }
  uint32_t riffSize = readLe32(riff + 4);
  uint32_t riffRemaining = 0;
  if (!resolveRiffRemaining(riffSize, responseLength, riffRemaining)) {
    return false;
  }

  bool validFormat = false;
  while (riffRemaining >= 8) {
    uint8_t header[8];
    if (!readExact(stream, header, sizeof(header))) {
      return false;
    }
    riffRemaining -= sizeof(header);
    uint32_t chunkSize = readLe32(header + 4);
    uint32_t padding = chunkSize & 1U;
    if (chunkSize > riffRemaining || padding > riffRemaining - chunkSize) {
      return false;
    }

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
      uint32_t byteRate = readLe32(format + 8);
      uint16_t blockAlign = readLe16(format + 12);
      uint16_t bitsPerSample = readLe16(format + 14);
      if (!skipBytes(stream, chunkSize - 16) ||
          (padding && !skipBytes(stream, padding))) {
        return false;
      }
      riffRemaining -= chunkSize;
      riffRemaining -= padding;
      validFormat =
          audioFormat == 1 && channels == 1 && sampleRate == 24000 &&
          byteRate == 48000 && blockAlign == 2 && bitsPerSample == 16;
      continue;
    }

    if (memcmp(header, "data", 4) == 0) {
      if (!validFormat || chunkSize == 0 || (chunkSize & 1U) != 0) {
        return false;
      }
      dataLength = chunkSize;
      return true;
    }

    if (!skipBytes(stream, chunkSize) ||
        (padding && !skipBytes(stream, padding))) {
      return false;
    }
    riffRemaining -= chunkSize;
    riffRemaining -= padding;
  }
  return false;
}

bool playTts(const char* text) {
  HTTPClient http;
  http.setTimeout(HTTP_CLIENT_TIMEOUT_MS);
  if (!http.begin(TTS_SERVER_URL)) {
    Serial.println("无法连接 TTS 地址");
    return false;
  }

  const char* responseHeaders[] = {"Content-Type"};
  http.collectHeaders(responseHeaders, 1);
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
  int parameterStart = contentType.indexOf(';');
  if (parameterStart >= 0) {
    contentType.remove(parameterStart);
  }
  contentType.trim();
  contentType.toLowerCase();
  if (contentType != "audio/wav") {
    Serial.printf("响应不是 WAV：%s\n", contentType.c_str());
    http.end();
    return false;
  }

  WiFiClient* stream = http.getStreamPtr();
  stream->setTimeout(HTTP_TIMEOUT_MS);
  uint32_t sampleRate = 0;
  uint32_t dataLength = 0;
  if (!findPcmData(*stream, http.getSize(), sampleRate, dataLength)) {
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
    size_t wanted = min(static_cast<uint32_t>(sizeof(buffer)), remaining);
    int received = stream->readBytes(reinterpret_cast<char*>(buffer), wanted);
    if (received <= 0) {
      Serial.println("音频流提前中断");
      releaseI2S();
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
      releaseI2S();
      http.end();
      return false;
    }
    remaining -= static_cast<uint32_t>(received);
  }

  bool drained = drainI2S(sampleRate);
  releaseI2S();
  http.end();
  if (!drained) {
    Serial.println("I2S 尾音排空失败");
    return false;
  }
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
  if (strlen(WIFI_SSID) == 0 || strlen(TTS_SERVER_URL) == 0 ||
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
