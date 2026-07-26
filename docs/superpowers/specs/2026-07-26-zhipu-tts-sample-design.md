# 智谱 TTS 试听样音设计

## 目标

使用项目现有的智谱 API Key 调用官方 GLM-TTS，生成一段可直接播放的中文 WAV 样音，用于判断智谱系统音色是否适合“芷春”。

## 范围

- 使用 `glm-tts` 模型和官方系统音色 `tongtong`（彤彤）。
- 生成约 15 秒的“芷春”中文自我介绍。
- 将样音保存为本地文件 `outputs/zhipu-tts-sample.wav`。
- 校验接口响应、音频格式和文件可播放性。

本次不修改现有 FastAPI、命令行聊天或 WebSocket 接口，不进行音色复刻，也不保存或输出 API Key。

## 实现方式

通过现有 `requests` 依赖直接请求智谱官方文本转语音接口：

`POST https://open.bigmodel.cn/api/paas/v4/audio/speech`

请求使用 `glm-tts`、`tongtong` 和 WAV 输出格式。API Key 仅从现有 `.env` 中读取并放入认证请求头。

直接调用 HTTP 接口比新增 SDK 更轻量，也避免将一次试听扩展成正式产品接入。

## 数据流

`试听文本 + 系统音色 -> 智谱 GLM-TTS -> WAV 响应 -> 本地样音文件`

## 错误处理

- API Key 缺失时停止并提示配置问题。
- HTTP 请求失败时不写入伪音频文件，并显示智谱返回的非敏感错误信息。
- 响应不是有效音频时停止，不把 JSON 错误内容保存成 WAV。
- 输出文件写入成功后检查文件类型、大小和音频时长。

## 验收标准

- `outputs/zhipu-tts-sample.wav` 存在且文件大小大于零。
- 文件可识别为 WAV 音频并能正常播放。
- 样音内容与设计的“芷春”自我介绍一致。
- 现有应用代码和接口没有变化。
