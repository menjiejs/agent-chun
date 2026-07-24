# IndexTTS-2 Local Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Apple M4、16GB 内存的 Mac 上隔离部署 IndexTTS-2，启动本地 WebUI，并生成可播放的中文验收样音。

**Architecture:** IndexTTS-2 作为 `local_tts/indextts2/` 下的独立应用运行，使用 Python 3.11、`uv` 和 Apple MPS，不与现有 FastAPI 进程共享解释器或依赖。模型和生成文件不进入 Git；本阶段只验证本地试听，后续再通过内部 HTTP 接入 FastAPI。

**Tech Stack:** Python 3.11、uv、PyTorch MPS、IndexTTS-2、ModelScope、Gradio、FFmpeg

## Global Constraints

- 只使用 IndexTTS-2 官方仓库和官方模型。
- WebUI 仅监听 `127.0.0.1:7860`。
- 禁用 CUDA、DeepSpeed、CUDA kernel 和 FP16。
- 只允许单任务生成。
- 参考音频必须是用户有权使用的声音。
- 不修改现有 `/chat` 接口，不加入语音识别，不提供公网访问。
- 模型、虚拟环境和生成音频不提交到 Git。

---

### Task 1: 隔离本地 TTS 文件

**Files:**
- Create: `.gitignore`
- Create: `docs/runbooks/indextts2-local.md`

**Interfaces:**
- Consumes: 当前仓库根目录 `/Users/yyz/agent`
- Produces: 被 Git 忽略的 `local_tts/` 目录和可重复执行的本地运行说明

- [ ] **Step 1: 添加本地模型忽略规则**

创建 `.gitignore`：

```gitignore
local_tts/
```

- [ ] **Step 2: 验证忽略规则**

Run:

```bash
mkdir -p local_tts/ignore-check
git check-ignore -v local_tts/ignore-check
```

Expected: 输出 `.gitignore:1:local_tts/`。

- [ ] **Step 3: 写入运行说明骨架**

创建 `docs/runbooks/indextts2-local.md`，记录安装位置、启动地址、停止方式、参考音频要求和 MPS 限制。命令以实际验证成功的命令为准，不记录未经验证的替代方案。

- [ ] **Step 4: 提交隔离规则**

```bash
git add .gitignore docs/runbooks/indextts2-local.md
git commit -m "准备 IndexTTS2 本地运行目录"
```

### Task 2: 准备 Python 3.11 环境

**Files:**
- Runtime: `local_tts/indextts2/.venv/`

**Interfaces:**
- Consumes: Homebrew 或系统中可用的 Python 3.11、FFmpeg、Git LFS、uv
- Produces: 能运行 `python --version` 和 `ffmpeg -version` 的隔离环境

- [ ] **Step 1: 检查工具**

Run:

```bash
command -v python3.11
command -v uv
command -v ffmpeg
command -v git-lfs
```

Expected: 每个命令都返回一个可执行文件路径。

- [ ] **Step 2: 安装缺失工具**

仅安装缺失项：

```bash
brew install python@3.11 uv ffmpeg git-lfs
git lfs install
```

- [ ] **Step 3: 验证版本**

Run:

```bash
python3.11 --version
uv --version
ffmpeg -version
git lfs version
```

Expected: Python 为 `3.11.x`，其余命令正常退出。

### Task 3: 下载官方代码和模型

**Files:**
- Runtime: `local_tts/indextts2/`
- Runtime: `local_tts/indextts2/checkpoints/`

**Interfaces:**
- Consumes: `https://github.com/index-tts/index-tts.git`、ModelScope 模型 `IndexTeam/IndexTTS-2`
- Produces: 安装完成的 IndexTTS-2 和完整 checkpoints

- [ ] **Step 1: 克隆官方仓库**

```bash
git clone https://github.com/index-tts/index-tts.git local_tts/indextts2
```

- [ ] **Step 2: 创建并同步 WebUI 环境**

```bash
cd local_tts/indextts2
uv venv --python 3.11
uv sync --extra webui
```

Expected: `.venv/bin/python` 存在，且安装过程不包含 CUDA、DeepSpeed 或 flash-attn。

- [ ] **Step 3: 下载官方模型**

```bash
uv tool install modelscope
modelscope download --model IndexTeam/IndexTTS-2 --local_dir checkpoints
```

- [ ] **Step 4: 验证必要模型文件**

Run:

```bash
for file in bpe.model gpt.pth config.yaml s2mel.pth wav2vec2bert_stats.pt; do test -f "checkpoints/$file" || exit 1; done
```

Expected: exit code `0`。

### Task 4: 启动并验证本地 WebUI

**Files:**
- Runtime output: `local_tts/indextts2/outputs/acceptance.wav`
- Modify: `docs/runbooks/indextts2-local.md`

**Interfaces:**
- Consumes: 完整模型、用户有权使用的参考音频、中文测试文本
- Produces: `http://127.0.0.1:7860` 和可播放的中文 WAV

- [ ] **Step 1: 检查 MPS**

Run:

```bash
uv run python tools/gpu_check.py
```

Expected: PyTorch 检测到 Apple MPS；若未检测到，保留输出并停止继续集成。

- [ ] **Step 2: 启动本地 WebUI**

```bash
uv run webui.py --host 127.0.0.1 --port 7860
```

Expected: 浏览器可访问 `http://127.0.0.1:7860`，日志显示模型使用 `mps`。

- [ ] **Step 3: 生成验收样音**

使用用户有权使用的参考音频生成：

```text
晚上好，BOSS。今天辛苦了，剩下的事情交给我吧。
```

将结果保存为 `outputs/acceptance.wav`。

- [ ] **Step 4: 验证音频**

Run:

```bash
ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1 outputs/acceptance.wav
```

Expected: 输出大于 `0` 的时长。

- [ ] **Step 5: 连续生成测试**

连续生成三次短句，记录每次耗时和峰值内存。Expected: 三次均成功，进程未崩溃，系统未出现持续内存交换。

- [ ] **Step 6: 完成运行说明**

在 `docs/runbooks/indextts2-local.md` 中写入经过验证的启动、停止、生成和排错步骤，并注明模型许可仅按个人本地测试处理。

- [ ] **Step 7: 回归现有 FastAPI**

Run:

```bash
venv/bin/python -m pytest -q
```

Expected: 现有测试全部通过。

- [ ] **Step 8: 提交运行说明**

```bash
git add docs/runbooks/indextts2-local.md
git commit -m "记录 IndexTTS2 本地运行方法"
```
