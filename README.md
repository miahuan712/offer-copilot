# OfferCopilot · 秋招工作台

> 一个本地运行、以岗位 JD 为中心的求职工作台：解析岗位、管理投递、评估与定制简历、模拟面试、沉淀面经，一条龙帮你打赢秋招。

OfferCopilot 是一个基于 **FastAPI + SQLite** 的单机 Web 应用，数据全部保存在本地、隐私可控；模型层兼容任意 **OpenAI-compatible** 接口（DeepSeek / OpenCode Go / 通义千问 / 智谱 GLM / 豆包 / Kimi / 本地 Ollama 等）。

---

## ✨ 功能一览

### 📋 岗位管理
- 对话式粘贴 JD，AI 自动提取 **公司 / 岗位 / Base / 要求 / 截止时间**
- 表格管理投递进度、阶段、备注，支持自定义阶段

### 🎯 简历匹配与评估
- 上传 / 粘贴简历，维护多个求职方向版本
- 一键匹配：基于 JD 对简历做**分层加权评分**（核心匹配 70% + 潜力 20% + 格式 10%），输出前置否决项、证据链、弱点与建议
- 「匹配度」与「评估与改写」使用**同一评估引擎**，分数一致

### ✍️ 简历评估 + 定向改写
- **分组 prompt 两阶段**：先出完整评估报告，再从经历库匹配经历生成**一页定制简历**
- 保留原始简历完整板块结构，丰富内容、润色表达、自然注入 JD 关键词
- 要点格式统一为：`动作小标题：背景说明，用什么工具做了什么，达成了什么成果`
- 按**岗位类型维度**调整侧重（产品 / 数据 / 运营 / 市场 / 财务 / 技术）
- 生成结果可 **编辑 / AI 润色 / 复制 / 导出 PDF / 另存为简历版本**
- 导出的 PDF 支持**证件照**、公司·岗位·时间**三列排版**、中英文、自动换行、一页排版

### 🌐 简历翻译
- 一键生成**商务英语**版本（内置 LLM 翻译，可选接入 DeepL）
- 支持独立翻译现有简历，或翻译改写后的简历

### 🎤 模拟面试 + 复盘
- 4 种面试官人设、多种面试类型；基于 JD + 简历 + 面经出题、追问、逐题评分并生成评估报告
- **面试复盘**：记录真实面试问题 → 自动存入面经库「我的面试」→ 模拟面试学习你的真实面试风格（自我迭代）

### 📚 面经库
- 支持**链接抓取**（小红书 / 牛客 / 知乎等）与**批量导入多条链接**
- 小红书走 Playwright 分层抓取：直连 → 无头浏览器 → 视觉大模型转写图片笔记
- 文件夹分类、收藏、搜索

### 📮 秋招日报
- 把岗位数据包装成日报，一键推送飞书 / 定时自动推送

### 🧪 Prompt 评测
- 评测集 + Prompt 版本管理 + 多模型对比，量化 JD 解析准确率

### ⚙️ 多模型配置
- 支持任意 OpenAI-compatible 接口，模型配置表、一键切换、用量与成本统计

---

## 🚀 快速开始

### 方式一：Windows 一键启动（推荐）
1. 安装 [Python 3.10+](https://www.python.org/downloads/)（安装时勾选 **Add python.exe to PATH**）
2. 双击 `start.bat`（首次运行会自动安装依赖并打开浏览器）
3. 浏览器打开 <http://127.0.0.1:8500>

### 方式二：手动启动
```bash
pip install -r requirements.txt
# 可选：小红书链接抓取需要 Playwright 浏览器（不装则自动降级为直连/Jina）
python -m playwright install chromium
python -m uvicorn app:app --host 127.0.0.1 --port 8500
```

### 方式三：Docker
```bash
cp .env.example .env      # 填入你的模型配置
docker compose up -d
```

---

## ⚙️ 配置

复制 `.env.example` 为 `.env` 并填写（也可以直接在网页「⚙️ 设置」里配置，配置保存在本地数据库）：

```env
DEEPSEEK_BASE=https://api.deepseek.com
DEEPSEEK_KEY=sk-xxx
DEEPSEEK_MODEL=deepseek-chat
```

可选的飞书日报配置：

```env
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_CHAT_ID=oc_xxx
FEISHU_DAILY_ENABLED=0
```

> 支持 DeepSeek / OpenCode Go / 通义千问 / 智谱 GLM / 豆包 / Kimi / 本地 Ollama 等任意 OpenAI-compatible 服务。

---

## 🧱 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI + SQLite + requests |
| 前端 | 单文件原生 HTML / CSS / JS（`static/index.html`） |
| PDF | ReportLab（中英文字体、证件照、自动换行） |
| 抓取 | requests + Playwright（可选）+ Jina Reader |
| 推送 | 飞书开放平台 API |

---

## 📁 项目结构

```
offer-copilot/
├─ app.py             # 后端主程序（API + LLM 抽象 + 业务逻辑）
├─ xhs.py             # 小红书分层抓取（直连 / Playwright / CLI）
├─ resume_pdf.py      # 简历 PDF 渲染（中英文、证件照、三列排版、自动换行）
├─ feishu.py          # 飞书推送
├─ static/index.html  # 前端单页
├─ requirements.txt
├─ start.bat          # Windows 一键启动
├─ Dockerfile
├─ docker-compose.yml
├─ .env.example
└─ .github/workflows/ci.yml
```

---

## 🔒 隐私说明

所有数据（岗位、简历、面经、面试记录、API Key 等）都保存在本地 `jobs.db`，不会上传到任何服务器。`.env`、`jobs.db`、证件照/头像等私人文件已在 `.gitignore` 中忽略，**请勿提交到公开仓库**。

---

## 🗺️ Roadmap

- [ ] 简历模板可视化编辑
- [ ] 更多平台面经抓取适配
- [ ] 岗位推荐与投递提醒

---

## 📄 License

[MIT](LICENSE)
