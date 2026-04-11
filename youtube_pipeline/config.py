#!/usr/bin/env python3
"""
MiroFish v3.0 YouTube 自动分析 - 配置文件
API Keys 从 .env 文件读取，请勿硬编码。
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from monorepo root
_script_dir = Path(__file__).resolve().parent
_monorepo_root = _script_dir.parent.parent.parent  # youtube_pipeline -> MiroFish -> monorepo root
_env_path = _monorepo_root / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

# ============== 主开关 ==============
ENABLED = False  # 设置为 True 时启用自动处理；False 时只进行 --dry-run 或 --test

# ============== 阿里百炼配置 ==============
BAILIAN_API_KEY = os.environ.get("BAILIAN_API_KEY", "")  # 从 .env 文件读取
BAILIAN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
BAILIAN_MODEL = "qwen3.6-plus"  # 可选：qwen-turbo (更快更便宜), qwen3.6-plus (平衡), qwen3.5-plus (推荐), qwen-max (最高质量)

# ============== Tavily 搜索配置 ==============
TAVILY_API_KEY = "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"
TAVILY_MAX_RESULTS = 5  # 每份报告中搜索返回的结果条数

# ============== 路径配置（相对路径） ==============
CHANNELS = ["Henry 的慢思考", "老厉害"]
YOUTUBE_DIR = str(_monorepo_root / "data" / "raw" / "media" / "youtube_downloads")
REPORTS_DIR = str(_monorepo_root / "data" / "reports" / "youtube")
CHECKLIST_PATH = str(_script_dir / "checklist.json")
MIROFISH_SPEC_PATH = str(_monorepo_root / "mirofish_v3_spec.md")  # v3 默认
MIROFISH_V4_SPEC_PATH = str(_monorepo_root / "src" / "analysis" / "mirofish" / "mirofish_v4_spec.md")

# ============== 报告格式 ==============
REPORT_DATE_FORMAT = "%Y%m%d"  # YYYYMMDD
REPORT_FILENAME_TEMPLATE = "{date}_{video_id}_MiroFish.md"
