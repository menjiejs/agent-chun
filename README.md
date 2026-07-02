# 芷春 Agent

一个命令行私人助理 agent，支持技能人格、连续对话历史和工具调用。

## 功能

- 默认技能：芷春
- 支持连续上下文对话
- 支持技能切换
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
```

## 启动

```bash
source venv/bin/activate
python agent1.py
```

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
agent1.py          命令行入口
skills/            技能人格
tools/             工具声明和工具实现
docs/              项目记录
requirements.txt   Python 依赖
.env.example       环境变量模板
```
