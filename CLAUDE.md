# MiroFish 模块

## 职责
报告生成引擎 + YouTube 分析流水线。Flask 后端 + Vue.js 前端，支持多代理模拟、知识图谱生成、投资分析报告。

## 目录结构
- `backend/` — Flask API + Vue 前端（原始 MiroFish 代码）
- `frontend/` — Vue.js SPA
- `scripts/mirofish/` — 场景分析、每日模拟、LLM 代理
- `youtube_pipeline/` — YouTube 下载 → 转录 → 报告生成流水线

## 依赖
- Python 3.12（backend 使用 .venv312）
- Node.js（前端）
- Whisper（本地转录）
- BAILIAN_API_KEY（阿里云 DashScope LLM）
- Tavily API（搜索）

## 路径约定
所有路径相对于 mono 仓库根目录。使用 `MONO_ROOT` 环境变量或 `Path(__file__).resolve().parent` 链式向上定位。

## 关键配置文件
- `youtube_pipeline/config.py` — YouTube 流水线配置（下载目录、报告目录等）
- `youtube_pipeline/config.json` — 下载配置
- `scripts/mirofish/` — 各脚本的 `.env` 路径和 `sys.path` 设置
