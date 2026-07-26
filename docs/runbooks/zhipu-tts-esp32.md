# ESP32 智谱 TTS 运行手册

本手册用于在 Mac 上运行语音服务，并让同一 Wi-Fi 内的 ESP32 通过 MAX98357 播放合成语音。当前实机是经典 ESP32-D0WDQ6，PlatformIO 环境为 `esp32dev`，串口为 `/dev/cu.usbserial-110`。文末同时保留 ESP32-S3 DevKitC-1 的参考配置。

## 1. 准备 Mac 服务

Mac 和 ESP32 必须连接同一个 Wi-Fi。复制环境变量模板：

```bash
cp .env.example .env
```

在 Mac 的 `.env` 中配置：

```env
ZHIPU_API_KEY=你的智谱 API Key
API_TOKEN=你的服务访问密码
HOST=0.0.0.0
```

`HOST=0.0.0.0` 是 ESP32 从局域网访问 Mac 服务的必要配置。不要通过路由器端口转发将 8000 端口暴露到公网。

查询 Mac 的局域网 IPv4：

```bash
ipconfig getifaddr en0
```

启动服务：

```bash
source venv/bin/activate
python server.py
```

语音接口格式如下：

```http
POST /tts
Authorization: Bearer 本机配置的服务访问密码
Content-Type: application/json

{"text":"你好，我是芷春"}
```

成功响应的内容类型为 `audio/wav`。

## 2. 配置 ESP32

复制固件密钥模板。生成的 `secrets.h` 已被忽略，不应提交：

```bash
cp firmware/esp32-tts/include/secrets.example.h \
  firmware/esp32-tts/include/secrets.h
```

编辑 `firmware/esp32-tts/include/secrets.h`：

- 填写 ESP32 要连接的 Wi-Fi 名称和密码。
- 将 `TTS_SERVER_URL` 设为 Mac 局域网 IPv4、服务端口和 `/tts` 路径，例如 `http://192.168.1.20:8000/tts`。
- 将 `SERVICE_API_TOKEN` 设为与 Mac `.env` 中 `API_TOKEN` 完全相同的值。

Mac 的局域网 IPv4 变化后，也要同步更新 `TTS_SERVER_URL`。

## 3. 连接 MAX98357

操作接线前先断开开发板电源。MAX98357 的 VIN 接 5V，GND 接开发板公共地；扬声器只能接在功放板的 SPK+ 和 SPK- 之间，不能将任一扬声器端接地。

### 经典 ESP32-D0WDQ6（`esp32dev`）

| MAX98357 | ESP32 |
| --- | --- |
| BCLK | GPIO26 |
| LRC / WS | GPIO25 |
| DIN | GPIO22 |
| VIN | 5V |
| GND | GND（公共地） |
| SPK+ / SPK- | 扬声器两端 |

### ESP32-S3 DevKitC-1（`esp32-s3-devkitc-1`）

| MAX98357 | ESP32-S3 |
| --- | --- |
| BCLK | GPIO16 |
| LRC / WS | GPIO17 |
| DIN | GPIO18 |
| VIN | 5V |
| GND | GND（公共地） |
| SPK+ / SPK- | 扬声器两端 |

## 4. 构建、烧录和查看串口

使用与开发板匹配的 PlatformIO 环境。当前经典 ESP32 的构建命令：

```bash
/Users/yyz/.platformio/penv/bin/pio run \
  -d firmware/esp32-tts \
  -e esp32dev
```

连接当前实机后烧录，并以 115200 波特率查看串口：

```bash
/Users/yyz/.platformio/penv/bin/pio device list
/Users/yyz/.platformio/penv/bin/pio run \
  -d firmware/esp32-tts \
  -e esp32dev \
  -t upload \
  --upload-port /dev/cu.usbserial-110
/Users/yyz/.platformio/penv/bin/pio device monitor \
  -p /dev/cu.usbserial-110 \
  -b 115200
```

ESP32-S3 DevKitC-1 使用对应环境：

```bash
/Users/yyz/.platformio/penv/bin/pio run \
  -d firmware/esp32-tts \
  -e esp32-s3-devkitc-1
/Users/yyz/.platformio/penv/bin/pio run \
  -d firmware/esp32-tts \
  -e esp32-s3-devkitc-1 \
  -t upload
/Users/yyz/.platformio/penv/bin/pio device monitor -b 115200
```

如果设备名变化，先运行 `pio device list`，再把实际串口传给上传和监视命令。

## 5. 验收 Mac 语音接口

服务使用已配置的 `.env` 启动后，在另一个终端执行：

```bash
mkdir -p outputs
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

验收结果应满足：

- `curl` 返回 HTTP 200。
- `file` 将文件识别为 RIFF/WAVE PCM。
- `afinfo` 报告 24 kHz、16-bit、单声道音频。

## 6. 验收硬件播放

串口应看到 Wi-Fi 连接成功信息（`已连接，IP：...`）和最终的 `播放完成`。固件只有在 TTS 返回 HTTP 200、Content-Type 与 WAV/PCM 格式校验通过、音频数据完整写入 I2S，并且尾音排空成功后，才会输出 `播放完成`。连续复位三次，三次都应完整播放，不应出现截断或持续噪声。

## 7. 排错

- ESP32 无法连接服务：确认 Mac 和 ESP32 在同一 Wi-Fi，`.env` 中有 `HOST=0.0.0.0`，并确认 `TTS_SERVER_URL` 使用 Mac 局域网 IPv4 而不是 `127.0.0.1`。
- 返回 401：确认 `SERVICE_API_TOKEN` 与 Mac `.env` 中的 `API_TOKEN` 完全一致。
- 上传失败：运行 `pio device list` 确认串口，并选择与开发板匹配的 PlatformIO 环境。
- 串口乱码：确认监视器波特率为 115200。
- 没有声音或持续噪声：断电后重新核对对应板型的 BCLK、LRC/WS、DIN，以及 5V 和公共地；确认扬声器只接 SPK+ 与 SPK-。
- WAV 不受支持：先按本手册验收 Mac 接口，确认输出为 24 kHz、16-bit、单声道 PCM WAV。
