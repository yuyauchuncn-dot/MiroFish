"""
Evidence Collector — 终极信息源采集系统

统一数据目录，为 MiroFish 报告提供基于事实的证据来源。
所有路径基于 monorepo 根目录，使用 lib.path_utils 解析。
"""

import os
import sys
from pathlib import Path


def _find_mono_root() -> Path:
    """Find monorepo root."""
    env_root = os.environ.get("MONO_ROOT")
    if env_root:
        return Path(env_root).resolve()
    try:
        from lib.path_utils import mono_root
        return mono_root()
    except Exception:
        pass
    # Fallback: walk up from this file (src/evidence/config.py → monorepo root)
    p = Path(__file__).resolve()
    for _ in range(8):
        if (p / "monodata").exists() and (p / "mirofish").exists():
            return p
        p = p.parent
    return Path(__file__).resolve().parent.parent.parent.parent


_MONO_ROOT = _find_mono_root()

# Use env_resolver for all DB paths (respects MONODATA_ENV for staging)
if str(_MONO_ROOT) not in sys.path:
    sys.path.insert(0, str(_MONO_ROOT))
import lib.env_loader  # 确保 .env 已加载（FRED_API_KEY 等）
from monodata.lib.env_resolver import db_path as _env_db_path

DB_DIR = _MONO_ROOT / "monodata" / "db"  # legacy compat
PROJECT_ROOT = _MONO_ROOT  # legacy compat for entityrelationshipweb
NEWS_DB = _env_db_path("news.db")
TWEETS_DB = _env_db_path("tweets.db")
PODCASTS_DB = _env_db_path("podcasts.db")
VIDEOS_DB = _env_db_path("videos.db")
RESEARCH_DB = _env_db_path("research.db")
FILINGS_DB = _env_db_path("filings.db")
CALENDARS_DB = _env_db_path("calendars.db")
MARKET_DATA_DB = _env_db_path("market_data.db")
SOURCES_DB = _env_db_path("evidence_sources.db")

# Independent evidence DBs
SEC_FILINGS_DB = _env_db_path("sec_filings.db")
IMPORTANT_PERSONS_DB = _env_db_path("important_persons.db")
RESEARCH_REPORTS_DB = _env_db_path("research_reports.db")
CHINA_COMPANIES_DB = _env_db_path("china_companies.db")
COMPANY_FUNDAMENTALS_DB = _env_db_path("company_fundamentals.db")
THIRTEEN_F_DB = _env_db_path("thirteen_f.db")
MARKET_INTELLIGENCE_DB = _env_db_path("market_intelligence.db")
MACRO_ECONOMIC_DB = _env_db_path("macro_economic.db")
ENTITY_GRAPH_DB = _env_db_path("entity_graph.db")

# Livenews DB
LIVENEWS_DB = _env_db_path("livenews.db")

# Legacy paths (kept for compatibility, may not exist in monorepo)
EVIDENCE_DIR = _MONO_ROOT / "data" / "evidence"
EVIDENCE_RAW_DIR = EVIDENCE_DIR / "raw"
EVIDENCE_INDEX_DIR = EVIDENCE_DIR / "index"
RAW_TWITTER_DIR = _MONO_ROOT / "data" / "raw" / "social-media" / "twitter"
RAW_RSS_DIR = _MONO_ROOT / "data" / "raw" / "social-media" / "rss"
RAW_XIAOYUZHOU_DIR = _MONO_ROOT / "data" / "raw" / "social-media" / "xiaoyuzhoufm"

# FRED API key（从 monorepo .env 加载）
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")

# Cookie files
TWITTER_COOKIES = EVIDENCE_RAW_DIR / "twitter_cookies.txt"
XUEQIU_COOKIES = EVIDENCE_RAW_DIR / "xueqiu_cookies.txt"

# Log directory
LOG_DIR = _MONO_ROOT / "logs" / "evidence"
