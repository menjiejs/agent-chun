# 芷春 Agent

一个命令行私人助理 agent，支持技能人格、连续对话历史、工具调用和 FastAPI 服务接口。

## 功能

- 默认技能：芷春
- 支持连续上下文对话
- 支持技能切换
- 支持 FastAPI HTTP 接口和 WebSocket 流式输出
- 支持 `session_id` 多会话
- 使用 SQLite 保存历史
- 支持高德天气工具
- 使用智谱 GLM 兼容 OpenAI SDK 的接口

## 安装

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 配置

复制环境变量模板：

```bash
cp .env.example .env
```

然后在 `.env` 中填写：

```env
ZHIPU_API_KEY=你的智谱 API Key
AMAP_WEATHER_KEY=你的高德天气 API Key
API_TOKEN=你的服务访问密码
```

## 启动

启动命令行 agent：

```bash
source venv/bin/activate
python agent1.py
```

启动 HTTP 服务：

```bash
source venv/bin/activate
python server.py
```

也可以直接用 uvicorn 启动 FastAPI：

```bash
source venv/bin/activate
uvicorn app.server:app --reload
```

接口文档：

```text
http://127.0.0.1:8000/docs
```

打开接口文档后，点击右上角 `Authorize`，输入你的服务访问密码：

```text
你的服务访问密码
```

`/chat`、`/switch_skill` 和 `/ws/chat` 需要鉴权；`/health` 和 `/skills` 可以直接访问。

打开另一个终端验证服务：

```bash
curl http://127.0.0.1:8000/health
```

如果看到下面结果，就说明服务能跑：

```json
{"status": "ok"}
```

调用聊天接口：

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer 你的服务访问密码" \
  -d '{"session_id":"user-1","message":"你好，介绍一下你自己"}'
```

如果 agent 正常调用模型，会返回：

```json
{"session_id": "user-1", "reply": "这里是 agent 的回复内容"}
```

查看技能：

```bash
curl 'http://127.0.0.1:8000/skills?session_id=user-1'
```

切换技能：

```bash
curl -X POST http://127.0.0.1:8000/switch_skill \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer 你的服务访问密码" \
  -d '{"session_id":"user-1","skill_name":"chun"}'
```

WebSocket 流式聊天地址：

```text
ws://127.0.0.1:8000/ws/chat?token=你的服务访问密码
```

发送消息格式：

```json
{"session_id": "user-1", "message": "你好"}
```

服务端会依次返回：

```json
{"type": "start", "session_id": "user-1"}
{"type": "delta", "content": "流式片段"}
{"type": "done", "session_id": "user-1"}
```

## HTTP 接口

- `GET /health`：健康检查
- `GET /skills?session_id=user-1`：查看技能和当前会话技能
- `POST /switch_skill`：切换指定会话的技能，并清空该会话历史
- `POST /chat`：普通非流式聊天

## 多会话和历史

HTTP 请求和 WebSocket 消息都可以传 `session_id`：

```json
{"session_id": "user-1", "message": "你想对 agent 说的话"}
```

不传时默认使用：

```text
default
```

历史会保存到 SQLite：

```text
data/agent.db
```

`data/` 已经被 `.gitignore` 忽略，不会提交到仓库。

## 命令

```text
/skills      查看所有可用技能
/switch 名称 切换技能
/clear       清空对话历史
/history     查看对话历史
exit         退出
```

## 目录

```text
agent1.py          命令行入口（调用 app.agent）
server.py          服务入口（调用 app.server）
app/               agent、FastAPI HTTP/WebSocket、SQLite 历史存储
skills/            技能人格
tools/             工具声明和工具实现
docs/              项目记录
requirements.txt   Python 依赖
.env.example       环境变量模板
```
