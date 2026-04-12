"""
Evidence Collector — 终极信息源采集系统

统一数据目录，为 MiroFish 报告提供基于事实的证据来源。
所有路径基于 monorepo 根目录，使用 lib.path_utils 解析。
"""

import os
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

# Evidence DBs live under monodata/db/
DB_DIR = _MONO_ROOT / "monodata" / "db"
NEWS_DB = DB_DIR / "news.db"
TWEETS_DB = DB_DIR / "tweets.db"
PODCASTS_DB = DB_DIR / "podcasts.db"
VIDEOS_DB = DB_DIR / "videos.db"
RESEARCH_DB = DB_DIR / "research.db"
FILINGS_DB = DB_DIR / "filings.db"
CALENDARS_DB = DB_DIR / "calendars.db"
MARKET_DATA_DB = DB_DIR / "market_data.db"
SOURCES_DB = DB_DIR / "evidence_sources.db"

# Independent evidence DBs
SEC_FILINGS_DB = DB_DIR / "sec_filings.db"
IMPORTANT_PERSONS_DB = DB_DIR / "important_persons.db"
RESEARCH_REPORTS_DB = DB_DIR / "research_reports.db"
CHINA_COMPANIES_DB = DB_DIR / "china_companies.db"
COMPANY_FUNDAMENTALS_DB = DB_DIR / "company_fundamentals.db"
THIRTEEN_F_DB = DB_DIR / "thirteen_f.db"
MARKET_INTELLIGENCE_DB = DB_DIR / "market_intelligence.db"
MACRO_ECONOMIC_DB = DB_DIR / "macro_economic.db"
ENTITY_GRAPH_DB = DB_DIR / "entity_graph.db"

# Livenews DB
LIVENEWS_DB = _MONO_ROOT / "monodata" / "db" / "livenews.db"

# Legacy paths (kept for compatibility, may not exist in monorepo)
EVIDENCE_DIR = _MONO_ROOT / "data" / "evidence"
EVIDENCE_RAW_DIR = EVIDENCE_DIR / "raw"
EVIDENCE_INDEX_DIR = EVIDENCE_DIR / "index"
RAW_TWITTER_DIR = _MONO_ROOT / "data" / "raw" / "social-media" / "twitter"
RAW_RSS_DIR = _MONO_ROOT / "data" / "raw" / "social-media" / "rss"
RAW_XIAOYUZHOU_DIR = _MONO_ROOT / "data" / "raw" / "social-media" / "xiaoyuzhoufm"

# FRED API key — should move to .env
FRED_API_KEY = os.environ.get("FRED_API_KEY", "f36c1046c4022404c7e1234c2f1b64a5")

# Cookie files
TWITTER_COOKIES = EVIDENCE_RAW_DIR / "twitter_cookies.txt"
XUEQIU_COOKIES = EVIDENCE_RAW_DIR / "xueqiu_cookies.txt"

# Log directory
LOG_DIR = _MONO_ROOT / "logs" / "evidence"
