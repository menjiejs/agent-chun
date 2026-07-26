# 智谱 TTS 试听样音 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使用现有智谱 API Key 生成并验证一段可直接播放的“芷春”中文 WAV 样音。

**Architecture:** 通过一次非流式 HTTP 请求调用智谱 `glm-tts`，将成功响应直接保存为本地 WAV。生成过程不修改现有应用代码，API Key 只从 `.env` 加载且不进入命令输出或文件。

**Tech Stack:** 智谱 GLM-TTS HTTP API、curl、macOS `file`、`afinfo`

## Global Constraints

- 使用 `glm-tts` 模型和官方系统音色 `tongtong`（彤彤）。
- 输出文件固定为 `outputs/zhipu-tts-sample.wav`。
- 本次不修改 FastAPI、命令行聊天或 WebSocket 接口。
- 不进行音色复刻，不保存或输出 API Key。
- HTTP 失败或响应不是 WAV 时，不把错误响应当作样音交付。

---

### Task 1: 生成并验证试听样音

**Files:**
- Runtime output: `outputs/zhipu-tts-sample.wav`
- Verify unchanged: `app/server.py`
- Verify unchanged: `app/agent.py`

**Interfaces:**
- Consumes: `.env` 中的 `ZHIPU_API_KEY`、智谱 `POST /api/paas/v4/audio/speech`
- Produces: 可播放的 WAV 文件 `outputs/zhipu-tts-sample.wav`

- [ ] **Step 1: 记录现有应用文件状态并准备输出目录**

Run:

```bash
git diff -- app/server.py app/agent.py
mkdir -p outputs
```

Expected: `git diff` 无输出，`outputs/` 存在。

- [ ] **Step 2: 调用智谱 GLM-TTS**

Request body:

```json
{
  "model": "glm-tts",
  "input": "你好，BOSS，我是芷春。很高兴能用声音陪在你身边。以后无论是整理信息、安排计划，还是陪你聊聊天，我都会认真听你说，温柔又可靠地回应你。",
  "voice": "tongtong",
  "response_format": "wav"
}
```

Run the request with `.env` loaded into the process environment, an Authorization Bearer header using `ZHIPU_API_KEY`, `--fail-with-body`, and output path `outputs/zhipu-tts-sample.wav`.

Expected: HTTP 200，curl 退出码为 0，输出文件大小大于零。

- [ ] **Step 3: 验证文件格式和音频元数据**

Run:

```bash
file outputs/zhipu-tts-sample.wav
afinfo outputs/zhipu-tts-sample.wav
```

Expected: `file` 识别为 RIFF/WAVE 音频；`afinfo` 成功显示音频格式、采样率、声道和时长。

- [ ] **Step 4: 确认没有改动应用代码**

Run:

```bash
git diff --exit-code -- app/server.py app/agent.py
```

Expected: 退出码为 0，无差异。

- [ ] **Step 5: 交付样音**

在最终回复中提供 `outputs/zhipu-tts-sample.wav` 的可点击本地链接，并报告实际音频时长和文件大小。样音是本地运行产物，不提交 Git。
