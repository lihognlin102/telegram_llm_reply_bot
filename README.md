# Telegram 群组智能自动回复机器人（LLM 驱动）

## 📌 项目简介

本项目是一个 **Telegram 群组监听 + 大模型自动回复系统**，用于在指定群组中自动参与发言，适用于以下典型场景：

- Telegram 群 **灌水发言**
- 群内 **活跃度 / 积分获取**
- **抽奖参与**（需发言或互动）
- 群助手 / 自动陪聊 / AI 群成员

系统通过监听 Telegram 群消息，结合大语言模型（LLM）进行上下文理解与自动回复，实现 **低人工参与成本的持续活跃发言**。

---

## ✨ 核心特性

- ✅ 监听多个 Telegram 群组消息
- ✅ 支持多个 Telegram 账号（多 session）
- ✅ 自动过滤是否需要回复（避免刷屏）
- ✅ 接入任意大模型（OpenAI / 本地模型 / Ollama / 自建 API）
- ✅ 支持上下文对话（短上下文 / 滑动窗口）
- ✅ 支持随机延迟，模拟真人行为
- ✅ 可配置回复频率、防风控
- ✅ 易于二次扩展（积分规则 / 关键词触发）

---

## 🧱 系统架构

```text
Telegram 群消息
        ↓
Telegram Client（监听）
        ↓
消息过滤 / 规则判断
        ↓
Prompt 构造
        ↓
大语言模型（LLM）
        ↓
回复策略（延迟 / 随机化）
        ↓
Telegram 自动回复

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 获取 Telegram API 凭证

1. 访问 [https://my.telegram.org/apps](https://my.telegram.org/apps)
2. 登录你的 Telegram 账号
3. 创建新应用，获取 `API_ID` 和 `API_HASH`

### 3. 配置环境变量

创建 `.env` 文件（参考 `.env.example`）：

```env
# Telegram API 配置
API_ID=your_api_id_here
API_HASH=your_api_hash_here
PHONE_NUMBER=+8613800138000
MONITOR_GROUPS=-1001234567890,my_group_username

# LLM 配置（阿里云百炼）
LLM_API_KEY=sk-your_api_key_here
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus
```

### 4. 运行监听程序

```bash
python telegram_listener.py
```

首次运行会要求输入验证码（Telegram 会发送到你的手机），输入后即可开始监听。

---

## 📁 项目结构

```
telegram_llm_reply_bot/
├── README.md              # 项目说明
├── requirements.txt       # Python 依赖
├── config.py              # 配置管理
├── telegram_listener.py   # Telegram 监听主程序
└── .env                   # 环境变量配置（需自行创建）
```

---

## 📝 当前功能

### ✅ 已实现

- [x] Telegram 消息监听
- [x] 多群组监听支持
- [x] 消息日志记录
- [x] 配置管理

### 🚧 待实现

- [ ] 消息过滤规则
- [ ] LLM 集成
- [ ] 自动回复功能
- [ ] 延迟和随机化策略
- [ ] 上下文管理