#!/usr/bin/env python3
"""
本地研究数据库统一查询模块

优化策略（针对 8.5GB / 246 万条新闻的大数据库）:
1. 连接池 — 复用 SQLite 连接，避免频繁 open/close
2. FTS5 全文搜索 — 利用已有的 news_fts 虚拟表
3. 只读连接 — WAL 模式下支持并发读取
4. 精确列选择 — SELECT 仅需要的列，避免拉取 content 大字段
5. 时间窗口过滤 — published_at 范围缩小扫描
6. 重要性排序 — 优先返回 importance 高的记录
7. 结果缓存 — 相同查询短时间命中缓存

使用示例:
    queries = ResearchQueries()
    news = queries.search_news("NVIDIA OR NVDA OR 英伟达")
    reports = queries.search_research_reports("AI 芯片")
    filings = queries.search_sec_filings("MU")
    brief = queries.compile_brief("Micron (MU) 现在值得买吗？")
"""

import json
import logging
import sqlite3
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# monorepo 根目录 — research_queries.py 在 src/utils/ 下
def _find_mono_root() -> Path:
    import os
    env_root = os.environ.get("MONO_ROOT")
    if env_root:
        return Path(env_root).resolve()
    p = Path(__file__).resolve()
    for _ in range(8):
        if (p / "monodata").exists() and (p / "mirofish").exists():
            return p
        p = p.parent
    return Path(__file__).resolve().parent.parent.parent.parent

_MONO_ROOT = _find_mono_root()
_EVIDENCE_DIR = _MONO_ROOT / "monodata" / "db"
_LIVENEWS_DIR = _MONO_ROOT / "monodata" / "db"


# ── 结果缓存（LRU, 最多 64 个查询）─────────────────────────

class QueryCache:
    """简单 LRU 查询结果缓存"""

    def __init__(self, maxsize: int = 64, ttl: int = 300):
        """
        Args:
            maxsize: 最大缓存条目数
            ttl: 缓存有效期（秒）
        """
        self._cache: OrderedDict[str, Tuple[any, float]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl

    def get(self, key: str) -> Optional[any]:
        if key in self._cache:
            value, ts = self._cache.pop(key)
            if time.time() - ts < self._ttl:
                self._cache[key] = (value, ts)  # re-insert at end (LRU)
                return value
            else:
                self._cache.pop(key, None)
        return None

    def put(self, key: str, value: any):
        if key in self._cache:
            self._cache.pop(key)
        self._cache[key] = (value, time.time())
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)


# ── 连接管理器 ──────────────────────────────────────────────

class ConnectionPool:
    """SQLite 连接池 — 每个 DB 维护一个只读连接"""

    def __init__(self):
        self._connections: Dict[str, sqlite3.Connection] = {}

    def get(self, db_path: str) -> sqlite3.Connection:
        if db_path not in self._connections:
            conn = sqlite3.connect(str(db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA query_only=ON")  # 只读，不影响主库
            self._connections[db_path] = conn
        return self._connections[db_path]

    def close_all(self):
        for conn in self._connections.values():
            conn.close()
        self._connections.clear()


# ── 数据类 ──────────────────────────────────────────────

@dataclass
class NewsItem:
    """新闻条目摘要（不加载完整 content）"""
    id: str
    source: str
    title: str
    published_at: int
    importance: int
    markets: List[str] = field(default_factory=list)
    url: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "title": self.title,
            "published_at": self.published_at,
            "importance": self.importance,
            "markets": self.markets,
            "url": self.url,
        }

    def summary(self) -> str:
        ts = datetime.fromtimestamp(self.published_at / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        title = self.title.strip() if self.title else ""
        if not title:
            title = "(无标题)"
        return f"[{ts}] {title} (via {self.source}, importance={self.importance})"


@dataclass
class ResearchReport:
    id: str
    source: str
    title: str
    published_at: int
    content_snippet: str = ""

    def summary(self) -> str:
        ts = datetime.fromtimestamp(self.published_at / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        return f"[{ts}] {self.title} (via {self.source})"


@dataclass
class SECFiling:
    id: str
    company: str
    filing_type: str
    title: str
    published_at: int
    url: str = ""

    def summary(self) -> str:
        ts = datetime.fromtimestamp(self.published_at / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        return f"[{ts}] {self.filing_type} - {self.company}: {self.title}"


@dataclass
class ImportantPerson:
    name: str
    role: str
    org: str
    description: str = ""

    def summary(self) -> str:
        return f"{self.name} — {self.role} @ {self.org}"


@dataclass
class MarketDataPoint:
    date: str
    symbol: str
    open: float = 0
    high: float = 0
    low: float = 0
    close: float = 0
    volume: int = 0

    def summary(self) -> str:
        return f"{self.date}: {self.symbol} O={self.open} H={self.high} L={self.low} C={self.close}"


# ── 主查询类 ──────────────────────────────────────────────

class ResearchQueries:
    """本地数据库统一查询接口"""

    def __init__(self, evidence_dir: Path = _EVIDENCE_DIR):
        self.evidence_dir = evidence_dir
        self._pool = ConnectionPool()
        self._cache = QueryCache(maxsize=64, ttl=300)  # 5 分钟缓存
        self._db_counts_cache: Optional[Dict[str, int]] = None
        self._db_counts_timestamp: float = 0

    @property
    def news_db(self) -> Path:
        return self.evidence_dir / "news.db"

    @property
    def research_reports_db(self) -> Path:
        return self.evidence_dir / "research_reports.db"

    @property
    def sec_filings_db(self) -> Path:
        return self.evidence_dir / "sec_filings.db"

    @property
    def important_persons_db(self) -> Path:
        return self.evidence_dir / "important_persons.db"

    @property
    def market_data_db(self) -> Path:
        return self.evidence_dir / "market_data.db"

    @property
    def company_fundamentals_db(self) -> Path:
        return self.evidence_dir / "company_fundamentals.db"

    @property
    def thirteen_f_db(self) -> Path:
        return self.evidence_dir / "thirteen_f.db"

    @property
    def evidence_sources_db(self) -> Path:
        return self.evidence_dir / "evidence_sources.db"

    @property
    def macro_economic_db(self) -> Path:
        return self.evidence_dir / "macro_economic.db"

    @property
    def market_intelligence_db(self) -> Path:
        return self.evidence_dir / "market_intelligence.db"

    @property
    def livenews_db(self) -> Path:
        return _LIVENEWS_DIR / "livenews.db"

    def _conn(self, db_path: Path) -> sqlite3.Connection:
        return self._pool.get(str(db_path))

    def close(self):
        self._pool.close_all()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    # ── 新闻搜索（FTS5）──────────────────────────────────────

    def search_news(
        self,
        query: str,
        limit: int = 20,
        days_back: int = 180,
        min_importance: int = 0,
        language: str = None,
    ) -> List[NewsItem]:
        """FTS5 全文搜索新闻

        Args:
            query: FTS5 搜索表达式（支持 AND/OR/NEAR/前缀匹配）
            limit: 返回数量上限
            days_back: 只搜索最近 N 天的新闻（默认 180 天，减少 GDELT 海量数据干扰）
            min_importance: 最低重要性过滤
            language: 语言过滤（如 "zh", "en"）

        Returns:
            按 FTS5 rank 排序的新闻列表
        """
        cache_key = f"news:{query}:{limit}:{days_back}:{min_importance}:{language}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        # DB 中 published_at 为毫秒级
        cutoff = int(time.time() * 1000) - (days_back * 86400 * 1000)

        sql = """
            SELECT n.id, n.source, n.title, n.published_at,
                   n.importance, n.markets, n.url,
                   substr(n.content, 1, 120) as content_preview
            FROM news_fts fts
            JOIN news_items n ON n.rowid = fts.rowid
            WHERE news_fts MATCH ?
              AND n.published_at >= ?
              AND n.importance >= ?
        """
        params = [query, cutoff, min_importance]

        if language:
            sql += " AND n.language = ?"
            params.append(language)

        sql += " ORDER BY fts.rank LIMIT ?"
        params.append(limit)

        conn = self._conn(self.news_db)
        rows = conn.execute(sql, params).fetchall()

        results = []
        for r in rows:
            try:
                markets = json.loads(r["markets"]) if r["markets"] else []
            except (json.JSONDecodeError, TypeError):
                markets = []

            # wallstreetcn 标题嵌入在 content 开头（| 之前）
            title = r["title"] or ""
            if not title and r["source"] == "api.wallstreetcn":
                preview = r["content_preview"] or ""
                title = preview.split("|")[0] if "|" in preview else preview[:60]

            results.append(NewsItem(
                id=r["id"],
                source=r["source"],
                title=title,
                published_at=r["published_at"],
                importance=r["importance"],
                markets=markets,
                url=r["url"] or "",
            ))

        self._cache.put(cache_key, results)
        return results

    def search_news_snippet(
        self, query: str, limit: int = 5, days_back: int = 90
    ) -> str:
        """搜索新闻并返回格式化文本（适合注入 LLM prompt）"""
        items = self.search_news(query, limit=limit, days_back=days_back)
        if not items:
            return f"[未找到与 '{query}' 相关的近期新闻]"
        lines = [f"### 相关新闻（{len(items)} 条）"]
        for item in items:
            lines.append(f"- {item.summary()}")
        return "\n".join(lines)

    def get_news_content(
        self, item_id: str
    ) -> Optional[str]:
        """获取指定新闻的完整 content（按需加载，避免全量拉取）"""
        conn = self._conn(self.news_db)
        row = conn.execute(
            "SELECT content FROM news_items WHERE id = ?", (item_id,)
        ).fetchone()
        return row["content"] if row else None

    def search_news_by_symbols(
        self, symbols: List[str], limit: int = 30, days_back: int = 30
    ) -> List[NewsItem]:
        """按股票代码搜索新闻"""
        # 使用索引而非 FTS5，适合精确 symbol 匹配
        # DB 中 published_at 为毫秒级
        cutoff = int(time.time() * 1000) - (days_back * 86400 * 1000)
        pattern = "%{}%"
        conditions = " OR ".join(
            f"n.symbols LIKE ?" for _ in symbols
        )
        params = [pattern.format(s) for s in symbols] + [cutoff, limit]

        sql = f"""
            SELECT n.id, n.source, n.title, n.published_at,
                   n.importance, n.markets, n.url
            FROM news_items n
            WHERE ({conditions}) AND n.published_at >= ?
            ORDER BY n.importance DESC, n.published_at DESC
            LIMIT ?
        """

        conn = self._conn(self.news_db)
        rows = conn.execute(sql, params).fetchall()

        results = []
        for r in rows:
            try:
                markets = json.loads(r["markets"]) if r["markets"] else []
            except (json.JSONDecodeError, TypeError):
                markets = []
            results.append(NewsItem(
                id=r["id"],
                source=r["source"],
                title=r["title"] or "",
                published_at=r["published_at"],
                importance=r["importance"],
                markets=markets,
                url=r["url"] or "",
            ))
        return results

    # ── 研究报告搜索 ───────────────────────────────────────

    def search_research_reports(
        self, query: str, limit: int = 10
    ) -> List[ResearchReport]:
        """搜索研究报告"""
        conn = self._conn(self.research_reports_db)
        # 检查是否有 FTS
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%fts%'"
        ).fetchall()]

        if tables:
            rows = conn.execute(
                """SELECT n.id, n.source, n.title, n.published_at,
                          substr(n.content, 1, 300) as snippet
                   FROM news_items n
                   WHERE n.title LIKE ? OR n.content LIKE ?
                   ORDER BY n.published_at DESC
                   LIMIT ?""",
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, source, title, published_at,
                          substr(content, 1, 300) as snippet
                   FROM news_items
                   WHERE title LIKE ? OR content LIKE ?
                   ORDER BY published_at DESC
                   LIMIT ?""",
                (f"%{query}%", f"%{query}%", limit),
            ).fetchall()

        return [
            ResearchReport(
                id=r["id"], source=r["source"], title=r["title"] or "",
                published_at=r["published_at"],
                content_snippet=r.get("snippet", ""),
            )
            for r in rows
        ]

    # ── SEC Filings 搜索 ───────────────────────────────────────

    def search_sec_filings(
        self, company: str, filing_type: str = None, limit: int = 10
    ) -> List[SECFiling]:
        """搜索 SEC 文件"""
        conn = self._conn(self.sec_filings_db)

        # 精确匹配: 先查 symbols 字段，再查 title
        sql = """
            SELECT id, source, title, published_at, url, symbols
            FROM news_items
            WHERE symbols LIKE ?
               OR title LIKE ?
               OR content LIKE ?
        """
        params = [f"%{company}%", f"%{company}%", f"%{company}%"]

        if filing_type:
            sql += " AND (title LIKE ? OR source LIKE ?)"
            params.extend([f"%{filing_type}%", f"%{filing_type}%"])

        sql += " ORDER BY published_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return [
            SECFiling(
                id=r["id"],
                company=r["source"].split(".")[-1] if "." in (r["source"] or "") else r["source"],
                filing_type="filing",
                title=r["title"] or "",
                published_at=r["published_at"],
                url=r["url"] or "",
            )
            for r in rows
        ]

    # ── 重要人物 ───────────────────────────────────────

    def find_persons(self, name: str, limit: int = 5) -> List[ImportantPerson]:
        """按名字搜索重要人物（通过 persona 字段）"""
        conn = self._conn(self.important_persons_db)
        rows = conn.execute(
            """SELECT persona, source, title, content
               FROM news_items
               WHERE persona LIKE ?
               LIMIT ?""",
            (f"%{name}%", limit),
        ).fetchall()

        # Fallback: FTS5 search on social_posts
        if not rows:
            try:
                rows = conn.execute(
                    """SELECT persona, persona as source,
                              substr(text, 1, 100) as title
                       FROM social_posts
                       WHERE persona LIKE ?
                       LIMIT ?""",
                    (f"%{name}%", limit),
                ).fetchall()
            except sqlite3.OperationalError:
                pass

        results = []
        for r in rows:
            d = dict(r)
            results.append(ImportantPerson(
                name=d.get("persona", "") or d.get("source", ""),
                role=d.get("source", ""),
                org="",
                description=(d.get("title") or "")[:200],
            ))
        return results

    # ── 市场数据 ───────────────────────────────────────

    def get_market_data(
        self, symbols: List[str], days: int = 30
    ) -> Dict[str, List[MarketDataPoint]]:
        """查询市场日线数据

        Args:
            symbols: 股票代码列表
            days: 最近 N 天

        Returns:
            {symbol: [data_points]}
        """
        conn = self._conn(self.market_data_db)

        # 探查表结构
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]

        result = {}
        for table in tables:
            for symbol in symbols:
                rows = conn.execute(
                    f"""SELECT * FROM {table}
                        WHERE ticker LIKE ?
                        ORDER BY date DESC
                        LIMIT ?""",
                    (f"%{symbol}%", days),
                ).fetchall()

                if rows:
                    points = []
                    for r in rows:
                        d = dict(r)
                        points.append(MarketDataPoint(
                            date=d.get("date", ""),
                            symbol=d.get("ticker", symbol),
                            open=d.get("open", 0),
                            high=d.get("high", 0),
                            low=d.get("low", 0),
                            close=d.get("close", 0),
                            volume=d.get("volume", 0),
                        ))
                    result[symbol] = points

        return result

    # ── 公司基本面（新增）──────────────────────────────────────

    def get_company_financials(self, symbol: str) -> Optional[Dict]:
        """查询公司最新财务指标

        Args:
            symbol: 股票代码（如 NVDA）

        Returns:
            {ticker, name, metrics: [...], latest_period}
        """
        conn = self._conn(self.company_fundamentals_db)

        # 查公司信息
        company = conn.execute(
            "SELECT cik, ticker, name, exchange, category FROM company_registry "
            "WHERE LOWER(ticker) = LOWER(?) OR LOWER(name) LIKE LOWER(?)",
            (symbol, f"%{symbol}%"),
        ).fetchone()

        if not company:
            return None

        cik = company["cik"]
        # 查最新一期财务指标
        metrics = conn.execute(
            """SELECT * FROM financial_metrics
               WHERE cik = ?
               ORDER BY period_end DESC
               LIMIT 1""",
            (cik,),
        ).fetchone()

        result = {
            "ticker": company["ticker"] or symbol,
            "name": company["name"],
            "exchange": company["exchange"],
            "category": company["category"],
            "cik": cik,
        }

        if metrics:
            result["latest_period"] = metrics["period_end"]
            result["fiscal_year"] = metrics["fiscal_year"]
            result["fiscal_period"] = metrics["fiscal_period"]
            result["gross_margin"] = metrics["gross_margin"]
            result["operating_margin"] = metrics["operating_margin"]
            result["net_margin"] = metrics["net_margin"]
            result["roe"] = metrics["roe"]
            result["debt_to_equity"] = metrics["debt_to_equity"]
            result["cash_ratio"] = metrics["cash_ratio"]
            result["revenue_yoy"] = metrics["revenue_yoy"]
            result["net_income_yoy"] = metrics["net_income_yoy"]
            result["eps_yoy"] = metrics["eps_yoy"]

        return result

    def get_company_financials_brief(self, symbol: str) -> str:
        """格式化为 LLM 可读文本"""
        data = self.get_company_financials(symbol)
        if not data:
            return f"[未找到 '{symbol}' 的公司财务数据]"

        lines = [f"### 公司基本面: {data['name']} ({data['ticker']})"]
        if data.get("exchange"):
            lines.append(f"- 交易所: {data['exchange']}")
        if data.get("category"):
            lines.append(f"- 分类: {data['category']}")

        if data.get("latest_period"):
            lines.append(f"\n#### 最新财务指标 (截至 {data['latest_period']}, FY{data.get('fiscal_year', '?')} Q{data.get('fiscal_period', '?')})")
            fmt = []
            for key, label in [
                ("gross_margin", "毛利率"), ("operating_margin", "营业利润率"),
                ("net_margin", "净利率"), ("roe", "ROE"),
                ("debt_to_equity", "负债/权益"), ("cash_ratio", "现金比率"),
                ("revenue_yoy", "营收YoY"), ("net_income_yoy", "净利润YoY"),
                ("eps_yoy", "EPS YoY"),
            ]:
                val = data.get(key)
                if val is not None:
                    pct = f"{val:.1%}" if abs(val) < 10 else f"{val:.1f}"
                    fmt.append(f"- {label}: {pct}")
            lines.extend(fmt)
        else:
            lines.append("- 暂无详细财务指标")

        return "\n".join(lines)

    # ── 13F 机构持仓（新增）──────────────────────────────────────

    def get_13f_holdings(self, manager: str = None, symbol: str = None) -> List[Dict]:
        """查询 13F 机构持仓

        Args:
            manager: 经理名称（模糊匹配，如 "Berkshire"）
            symbol: 发行人名称（模糊匹配，如 "NVDA" 或 "NVIDIA"）

        Returns:
            持仓列表
        """
        conn = self._conn(self.thirteen_f_db)

        if manager:
            # 按经理查询
            mgr = conn.execute(
                "SELECT cik, manager_name FROM thirteen_f_managers "
                "WHERE LOWER(manager_name) LIKE LOWER(?)",
                (f"%{manager}%",),
            ).fetchone()

            if not mgr:
                return []

            rows = conn.execute(
                """SELECT h.*, m.manager_name
                   FROM thirteen_f_holdings h
                   JOIN thirteen_f_managers m ON h.manager_cik = m.cik
                   WHERE h.manager_cik = ?
                   ORDER BY h.value DESC
                   LIMIT 30""",
                (mgr["cik"],),
            ).fetchall()

            return [dict(r) for r in rows]

        elif symbol:
            # 按股票查询（哪些机构持有）
            rows = conn.execute(
                """SELECT h.*, m.manager_name
                   FROM thirteen_f_holdings h
                   JOIN thirteen_f_managers m ON h.manager_cik = m.cik
                   WHERE LOWER(h.issuer_name) LIKE LOWER(?)
                      OR LOWER(h.title_of_class) LIKE LOWER(?)
                   ORDER BY h.value DESC
                   LIMIT 30""",
                (f"%{symbol}%", f"%{symbol}%"),
            ).fetchall()

            return [dict(r) for r in rows]

        return []

    def get_13f_brief(self, query: str) -> str:
        """格式化为 LLM 可读文本"""
        holdings = self.get_13f_holdings(manager=query) or self.get_13f_holdings(symbol=query)
        if not holdings:
            return f"[未找到与 '{query}' 相关的 13F 持仓]"

        # 判断是按经理还是按股票
        is_manager = "manager_name" in holdings[0] and holdings[0].get("manager_name")
        if len(holdings) > 1 and holdings[0].get("manager_name") == holdings[-1].get("manager_name"):
            lines = [f"### 13F 机构持仓: {holdings[0]['manager_name']}"]
            lines.append(f"- 持仓数量: {len(holdings)} 只")
            total_val = sum(h.get("value", 0) for h in holdings)
            lines.append(f"- 总市值: ${total_val/1e6:.0f}M")
            lines.append(f"- 报告日期: {holdings[0]['report_date']}")
            lines.append(f"\n#### Top 10 持仓")
            for h in holdings[:10]:
                pct = (h.get("value", 0) / max(total_val, 1)) * 100
                lines.append(f"- {h['issuer_name']}: ${h.get('value', 0)/1e6:.0f}M ({pct:.1f}%) | {h.get('shares', 0):,} 股")
        else:
            lines = [f"### 13F 持仓: {query}"]
            for h in holdings:
                lines.append(f"- {h['manager_name']}: ${h.get('value', 0)/1e6:.0f}M | {h.get('shares', 0):,} 股 | {h.get('report_date', '')}")
        return "\n".join(lines)

    # ── 数据源可信度（新增）──────────────────────────────────────

    def _count_db_rows_by_category(self) -> Dict[str, int]:
        """统计各证据数据库实际行数，按 category 分组"""
        if self._db_counts_cache and time.time() - self._db_counts_timestamp < 300:
            return self._db_counts_cache

        def _count(db_path: Path, table: str) -> int:
            try:
                conn = self._conn(db_path)
                return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except Exception:
                return 0

        counts: Dict[str, int] = {}

        news_count = _count(self.news_db, "news_items")
        counts["news"] = news_count
        counts["news_zh"] = news_count

        counts["analysis"] = _count(self.research_reports_db, "news_items")
        counts["macro"] = _count(self.macro_economic_db, "fred_observations")
        counts["fundamentals"] = _count(self.company_fundamentals_db, "company_registry")
        counts["holdings"] = _count(self.thirteen_f_db, "thirteen_f_holdings")

        counts["filings"] = (
            _count(self.sec_filings_db, "insider_trades") +
            _count(self.sec_filings_db, "market_history")
        )

        market_count = _count(self.market_data_db, "market_history")
        for table in ["cross_asset", "etf_flows", "market_breadth", "options_market",
                      "volatility_surface", "yield_curve", "daily_returns"]:
            market_count += _count(self.market_intelligence_db, table)
        counts["market_data"] = market_count

        counts["livenews"] = _count(self.livenews_db, "news_items")

        self._db_counts_cache = counts
        self._db_counts_timestamp = time.time()
        return counts

    def get_source_credibility(self, source: str = None, category: str = None) -> List[Dict]:
        """查询数据源可信度信息

        Args:
            source: 来源名称（模糊匹配）
            category: 来源类别（如 news, sec, twitter）

        Returns:
            来源列表
        """
        conn = self._conn(self.evidence_sources_db)

        conditions = []
        params = []
        if source:
            conditions.append("LOWER(name) LIKE LOWER(?)")
            params.append(f"%{source}%")
        if category:
            conditions.append("category = ?")
            params.append(category)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        rows = conn.execute(
            f"SELECT name, source_type, category, priority, enabled, total_fetched, last_fetch_at "
            f"FROM sources {where} ORDER BY priority DESC, total_fetched DESC LIMIT 50",
            params,
        ).fetchall()

        results = [dict(r) for r in rows]

        # 如果 total_fetched 全为 0（调度器从未运行），回退到实际数据库行数
        if results and all(r.get("total_fetched", 0) == 0 for r in results):
            db_counts = self._count_db_rows_by_category()
            for r in results:
                cat = r.get("category", "")
                if cat in db_counts:
                    r["total_fetched"] = db_counts[cat]

        return results

    def get_source_credibility_brief(self, source: str = None) -> str:
        """格式化为 LLM 可读文本"""
        sources = self.get_source_credibility(source=source)
        if not sources:
            return f"[未找到数据源 '{source}']"

        lines = [f"### 数据源可信度"]
        for s in sources:
            enabled = "✅ 启用" if s.get("enabled") else "❌ 禁用"
            lines.append(f"- {s['name']} ({s['category']}, {s['source_type']}): priority={s.get('priority', '?')} | {enabled} | 累计 {s.get('total_fetched', 0)} 条")
        return "\n".join(lines)

    # ── 重要人物内容增强（新增）──────────────────────────────────────

    def get_person_social_posts(self, name: str, limit: int = 10) -> List[Dict]:
        """查询人物的社交媒体帖子

        Args:
            name: 人物名称（模糊匹配）
            limit: 返回数量上限

        Returns:
            帖子列表
        """
        conn = self._conn(self.important_persons_db)
        try:
            rows = conn.execute(
                """SELECT persona, text, platform, posted_at
                   FROM social_posts
                   WHERE persona LIKE ?
                   ORDER BY posted_at DESC
                   LIMIT ?""",
                (f"%{name}%", limit),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.OperationalError:
            return []

    # ── SEC 文件全文（新增）──────────────────────────────────────

    def get_sec_filing_content(self, company: str, filing_type: str = None, limit: int = 5) -> List[Dict]:
        """查询 SEC 文件完整内容

        Args:
            company: 公司名/代码（模糊匹配）
            filing_type: 文件类型（如 10-K, 10-Q）
            limit: 返回数量上限

        Returns:
            包含完整 content 的文件列表
        """
        conn = self._conn(self.sec_filings_db)

        # 精确 ticker 匹配优先
        sql = """SELECT ticker, company_name, form_type, filed_date,
                        substr(content, 1, 2000) as content_preview,
                        content_length, url
                 FROM filing_documents
                 WHERE ticker = ?"""
        params = [company]

        if filing_type:
            sql += " AND form_type = ?"
            params.append(filing_type)

        sql += " ORDER BY filed_date DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(sql, params).fetchall()

        # 如果精确匹配无结果，尝试公司名模糊匹配
        if not rows and len(company) > 2:
            sql2 = """SELECT ticker, company_name, form_type, filed_date,
                             substr(content, 1, 2000) as content_preview,
                             content_length, url
                      FROM filing_documents
                      WHERE LOWER(company_name) LIKE LOWER(?)"""
            params2 = [f"%{company}%"]
            if filing_type:
                sql2 += " AND form_type = ?"
                params2.append(filing_type)
            sql2 += " ORDER BY filed_date DESC LIMIT ?"
            params2.append(limit)
            rows = conn.execute(sql2, params2).fetchall()

        return [dict(r) for r in rows]

    # ── 宏观经济数据（macro_economic.db）──────────────────────────

    def get_fred_series(self, series_id: str, limit: int = 12) -> List[Dict]:
        """查询指定 FRED 序列的最近 N 条观测值

        Args:
            series_id: FRED Series ID（如 CPIAUCSL, UNRATE）
            limit: 返回最近 N 条记录

        Returns:
            [{date, value}] 列表
        """
        conn = self._conn(self.macro_economic_db)
        rows = conn.execute(
            "SELECT date, value FROM fred_observations "
            "WHERE series_id = ? ORDER BY date DESC LIMIT ?",
            (series_id, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]  # 升序返回

    def get_fred_summary(self, series_ids: List[str]) -> str:
        """格式化多个 FRED 序列的最新值为 LLM 可读文本"""
        lines = []
        series_labels = {
            "CPIAUCSL": ("CPI 全部城市", ""),
            "CPILFESL": ("核心 CPI", ""),
            "PCEPILFE": ("核心 PCE", ""),
            "UNRATE": ("失业率", "%"),
            "FEDFUNDS": ("联邦基金利率", "%"),
            "DGS10": ("10Y 国债收益率", "%"),
            "DFII10": ("10Y TIPS 实际收益率", "%"),
            "T10Y2Y": ("10Y-2Y 利差", ""),
            "M2SL": ("M2 货币供应", "十亿美元"),
            "WALCL": ("美联储资产负债表", "十亿美元"),
            "RRPONTSYD": ("隔夜逆回购", "十亿美元"),
            "SOFR": ("SOFR", "%"),
            "STLFSI4": ("金融压力指数", ""),
            "BAMLH0A0HYM2": ("高收益债利差", "bps"),
            "BAMLC0A1CAAA": ("投资级利差", "bps"),
            "GDP": ("名义 GDP", "十亿美元"),
            "GDPC1": ("实际 GDP", "十亿美元"),
            "INDPRO": ("工业生产指数", ""),
            "TCU": ("产能利用率", "%"),
            "PAYEMS": ("非农就业", "千人"),
            "RSXFS": ("零售销售", "十亿美元"),
            "UMCSENT": ("消费者信心", ""),
            "CSUSHPISA": ("Case-Shiller 房价", ""),
            "MORTGAGE30US": ("30年房贷利率", "%"),
            "TEDRATE": ("TED 利差", "%"),
            # 中国系列
            "CPALTT01CNM659N": ("中国 CPI", "%"),
            "QCNN368BIS": ("中国房价指数 (BIS)", ""),
            "QCNR368BIS": ("中国实际房价 (BIS)", ""),
            "IR3TIB01CNM156N": ("中国 3M 同业利率", "%"),
            "INTDSRCNM193N": ("中国贴现率", "%"),
            "XTNTVA01CNM664S": ("中国贸易余额", "美元"),
            "MANMM101CNM189N": ("中国 M1", "元"),
            "EXCHUS": ("美元/人民币", ""),
            "CCRETT01CNM661N": ("人民币实际有效汇率", ""),
        }
        # Special unit overrides (raw FRED units differ from display units)
        fred_unit_overrides = {
            "WALCL": lambda v: f"${v/1e6:.2f}T",          # millions → trillions
            "RRPONTSYD": lambda v: f"${v*1e3:.0f}B",      # trillions → billions
            "M2SL": lambda v: f"${v/1e3:.1f}T",           # billions → trillions
            "GDP": lambda v: f"${v/1e3:.1f}T",            # billions → trillions
            "GDPC1": lambda v: f"${v/1e3:.1f}T",
            "PAYEMS": lambda v: f"{v/1e3:.1f}M",          # thousands → millions
        }
        for sid in series_ids:
            rows = self.get_fred_series(sid, limit=3)
            if rows:
                latest = rows[-1]
                label, unit = series_labels.get(sid, (sid, ""))
                val = latest["value"]
                if val is None:
                    val_str = "N/A"
                elif sid in fred_unit_overrides:
                    val_str = fred_unit_overrides[sid](val)
                else:
                    val_str = f"{val:.2f}{unit}" if unit else f"{val:,.2f}"
                lines.append(f"- **{label}** ({sid}): {val_str} (截至 {latest['date']})")
        return "\n".join(lines) if lines else "[无 FRED 数据]"

    def get_valuation_metrics(self, limit: int = 6) -> str:
        """S&P 500 估值指标摘要"""
        conn = self._conn(self.macro_economic_db)
        rows = conn.execute(
            "SELECT * FROM valuation_metrics ORDER BY date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        if not rows:
            return "[无估值数据]"

        lines = ["### S&P 500 估值"]
        for r in reversed(rows):
            d = dict(r)
            parts = [f"**{d['date']}**"]
            if d.get("sp500_pe"):
                parts.append(f"PE={d['sp500_pe']:.1f}x")
            if d.get("sp500_cape"):
                parts.append(f"CAPE={d['sp500_cape']:.1f}x")
            if d.get("earnings_yield"):
                parts.append(f"盈利收益率={d['earnings_yield']:.2f}%")
            if d.get("equity_risk_premium"):
                parts.append(f"ERP={d['equity_risk_premium']:.2f}%")
            lines.append("- " + " | ".join(parts))

        # 加历史分位参考
        latest = dict(rows[0])
        if latest.get("sp500_pe"):
            pe = latest["sp500_pe"]
            pe_level = "极高" if pe > 30 else "偏高" if pe > 22 else "合理" if pe > 15 else "偏低"
            lines.append(f"- 当前 PE {pe:.1f}x 处于历史 {pe_level} 区间 (历史均值 ~16x)")
        if latest.get("sp500_cape"):
            cape = latest["sp500_cape"]
            cape_level = "极高" if cape > 35 else "偏高" if cape > 25 else "合理" if cape > 17 else "偏低"
            lines.append(f"- 当前 CAPE {cape:.1f}x 处于历史 {cape_level} 区间 (历史均值 ~17x)")
        return "\n".join(lines)

    def get_energy_data(self, limit: int = 4) -> str:
        """能源数据摘要"""
        conn = self._conn(self.macro_economic_db)
        series_labels = {
            "crude_production": ("原油产量", "千桶/日"),
            "crude_stocks": ("原油库存", "百萬桶"),
            "spr_stocks": ("战略石油储备", "百萬桶"),
            "gasoline_stocks": ("汽油库存", "百萬桶"),
            "distillate_stocks": ("餾分油库存", "百萬桶"),
            "natural_gas_storage": ("天然气库存", "BCF"),
            "coal_production": ("煤炭产量", "千短噸"),
        }
        lines = ["### 能源数据 (EIA)"]
        for sid, (label, unit) in series_labels.items():
            rows = conn.execute(
                "SELECT date, value, unit FROM energy_data "
                "WHERE series_id = ? ORDER BY date DESC LIMIT 1",
                (sid,),
            ).fetchone()
            if rows:
                d = dict(rows)
                val = d["value"]
                u = d.get("unit") or unit
                lines.append(f"- **{label}**: {val:,.1f} {u} (截至 {d['date']})")
        return "\n".join(lines) if len(lines) > 1 else "[无能源数据]"

    def get_credit_markets(self, limit: int = 5) -> str:
        """信贷市场摘要 — 取各字段最新有效值"""
        conn = self._conn(self.macro_economic_db)

        # 各字段最新非 NULL 值可能在不同日期，分别查询
        fields = {
            "ted_spread": ("TED 利差", False),
            "hy_spread": ("高收益利差", True),
            "ig_spread": ("投资级利差", True),
            "financial_stress_index": ("金融压力指数", False),
            "mortgage_rate_30y": ("30年房贷", False),
            "spread_10y_2y": ("10Y-2Y 倒挂", False),
            "recession_prob": ("衰退概率", False),
        }

        lines = ["### 信贷市场"]
        for col, (label, is_bps) in fields.items():
            row = conn.execute(
                f"SELECT date, {col} FROM credit_markets "
                f"WHERE {col} IS NOT NULL ORDER BY date DESC LIMIT 1",
            ).fetchone()
            if row:
                val = row[1]
                if is_bps:
                    lines.append(f"- **{label}**: {val:.0f}bps (截至 {row[0]})")
                else:
                    lines.append(f"- **{label}**: {val:.2f} (截至 {row[0]})")
        return "\n".join(lines)

    # ── 市场情报（market_intelligence.db）─────────────────────────

    def get_volatility_surface(self, limit: int = 5) -> str:
        """波动率表面摘要"""
        conn = self._conn(self.market_intelligence_db)
        rows = conn.execute(
            "SELECT * FROM volatility_surface ORDER BY date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        if not rows:
            return "[无波动率数据]"

        lines = ["### 波动率表面"]
        for r in reversed(rows):
            d = dict(r)
            parts = [f"**{d['date']}**"]
            if d.get("vix"):
                parts.append(f"VIX={d['vix']:.1f}")
            if d.get("vvix"):
                parts.append(f"VVIX={d['vvix']:.1f}")
            if d.get("skew"):
                parts.append(f"SKEW={d['skew']:.1f}")
            if d.get("move"):
                parts.append(f"MOVE={d['move']:.1f}")
            if d.get("vxx_vixm_ratio"):
                parts.append(f"VXX/VIXM={d['vxx_vixm_ratio']:.2f}")
            lines.append("- " + " | ".join(parts))

        latest = dict(rows[0])
        if latest.get("vix"):
            vix = latest["vix"]
            vix_level = "极低" if vix < 13 else "偏低" if vix < 18 else "正常" if vix < 25 else "偏高" if vix < 35 else "恐慌"
            lines.append(f"- VIX {vix:.1f} 处于 {vix_level} 区间")
        return "\n".join(lines)

    def get_yield_curve(self, limit: int = 5) -> str:
        """收益率曲线摘要"""
        conn = self._conn(self.market_intelligence_db)
        rows = conn.execute(
            "SELECT * FROM yield_curve ORDER BY date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        if not rows:
            return "[无收益率曲线数据]"

        lines = ["### 国债收益率曲线"]
        for r in reversed(rows):
            d = dict(r)
            parts = [f"**{d['date']}**"]
            col_map = {"tbill_3m": "3M", "note_2y": "2Y", "note_5y": "5Y", "note_10y": "10Y", "bond_30y": "30Y"}
            for col, label in col_map.items():
                val = d.get(col)
                if val is not None:
                    parts.append(f"{label}={val:.2f}%")
            if d.get("spread_10y_2y") is not None:
                parts.append(f"10Y-2Y={d['spread_10y_2y']:.2f}")
            lines.append("- " + " | ".join(parts))
        return "\n".join(lines)

    def get_cross_asset_summary(self, limit: int = 5) -> str:
        """跨资产价格摘要"""
        conn = self._conn(self.market_intelligence_db)
        rows = conn.execute(
            "SELECT * FROM cross_asset ORDER BY date DESC LIMIT ?",
            (limit,),
        ).fetchall()
        if not rows:
            return "[无跨资产数据]"

        lines = ["### 跨资产价格"]
        for r in reversed(rows):
            d = dict(r)
            parts = [f"**{d['date']}**"]
            col_labels = {
                "gold": "黄金", "silver": "白银", "copper": "铜",
                "oil": "原油", "dxy": "DXY", "btc": "BTC", "sp500": "SP500",
            }
            for col, label in col_labels.items():
                val = d.get(col)
                if val is not None:
                    parts.append(f"{label}={val:,.2f}")
            lines.append("- " + " | ".join(parts))
        return "\n".join(lines)

    def get_put_call_ratio(self, tickers: List[str] = None, limit: int = 5) -> str:
        """期权 P/C Ratio 摘要"""
        conn = self._conn(self.market_intelligence_db)
        tickers = tickers or ["SPY", "QQQ", "SP500_AGG"]
        lines = ["### 期权 P/C Ratio"]
        for ticker in tickers:
            rows = conn.execute(
                "SELECT date, pc_volume_ratio, pc_oi_ratio, pc_combined "
                "FROM put_call_ratio WHERE ticker = ? "
                "ORDER BY date DESC LIMIT ?",
                (ticker, limit),
            ).fetchall()
            if rows:
                latest = dict(rows[0])
                parts = [f"**{ticker}**"]
                if latest.get("pc_volume_ratio"):
                    parts.append(f"Volume P/C={latest['pc_volume_ratio']:.2f}")
                if latest.get("pc_oi_ratio"):
                    parts.append(f"OI P/C={latest['pc_oi_ratio']:.2f}")
                sentiment = "恐慌" if latest.get("pc_combined", 1) > 1.2 else "乐观" if latest.get("pc_combined", 1) < 0.8 else "中性"
                parts.append(f"情绪={sentiment}")
                lines.append("- " + " | ".join(parts))
        return "\n".join(lines) if len(lines) > 1 else "[无期权数据]"

    def get_market_overview_brief(self) -> str:
        """综合市场概览 — 一次性拉取波动率 + 收益率 + 跨资产 + 期权"""
        sections = [
            self.get_volatility_surface(limit=3),
            self.get_yield_curve(limit=3),
            self.get_cross_asset_summary(limit=3),
            self.get_put_call_ratio(limit=3),
        ]
        return "\n\n".join(s for s in sections if s and not s.startswith("["))

    # ── LiveNews 实时新闻（monodata/db/livenews.db）────────────

    def search_livenews(self, query: str, limit: int = 10, days_back: int = 7) -> List[Dict]:
        """LiveNews FTS5 全文搜索

        Args:
            query: 搜索关键词
            limit: 返回数量
            days_back: 时间窗口（天）

        Returns:
            新闻记录列表
        """
        conn = self._conn(self.livenews_db)
        cutoff_ts = int((datetime.now(timezone.utc).timestamp() - days_back * 86400) * 1000)
        try:
            rows = conn.execute(
                "SELECT ni.id, ni.source, ni.title, ni.content, ni.published_at, "
                "ni.importance, ni.symbols, ni.topics, ni.markets "
                "FROM news_fts fts5 "
                "JOIN news_items ni ON ni.rowid = fts5.rowid "
                "WHERE news_fts MATCH ? AND ni.published_at >= ? "
                "ORDER BY ni.published_at DESC LIMIT ?",
                (query, cutoff_ts, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            # FTS 查询失败时回退到 LIKE 搜索
            rows = conn.execute(
                "SELECT id, source, title, content, published_at, importance, symbols, topics, markets "
                "FROM news_items "
                "WHERE content LIKE ? AND published_at >= ? "
                "ORDER BY published_at DESC LIMIT ?",
                (f"%{query}%", cutoff_ts, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_livenews_flash(self, limit: int = 15, hours: int = 24) -> List[Dict]:
        """获取最近 LiveNews 快讯（无关键词过滤）

        Args:
            limit: 返回数量
            hours: 时间窗口（小时）

        Returns:
            快讯记录列表
        """
        conn = self._conn(self.livenews_db)
        cutoff_ts = int((datetime.now(timezone.utc).timestamp() - hours * 3600) * 1000)
        rows = conn.execute(
            "SELECT id, source, title, content, published_at, importance, symbols, markets "
            "FROM news_items "
            "WHERE published_at >= ? "
            "ORDER BY importance DESC, published_at DESC LIMIT ?",
            (cutoff_ts, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_livenews_by_symbols(self, symbols: List[str], limit: int = 10, days_back: int = 7) -> List[Dict]:
        """按股票代码获取 LiveNews 新闻

        Args:
            symbols: 股票代码列表
            limit: 返回数量
            days_back: 时间窗口（天）

        Returns:
            新闻记录列表
        """
        conn = self._conn(self.livenews_db)
        cutoff_ts = int((datetime.now(timezone.utc).timestamp() - days_back * 86400) * 1000)
        all_results = []
        for sym in symbols[:5]:
            rows = conn.execute(
                "SELECT id, source, title, content, published_at, importance, symbols "
                "FROM news_items "
                "WHERE (content LIKE ? OR symbols LIKE ?) AND published_at >= ? "
                "ORDER BY published_at DESC LIMIT ?",
                (f"%{sym}%", f"%{sym}%", cutoff_ts, limit),
            ).fetchall()
            all_results.extend([dict(r) for r in rows])
        return all_results[:limit]

    # ── 综合简报 v4（增强版）──────────────────────────────────────

    def compile_brief(
        self,
        topic: str,
        keywords: Optional[List[str]] = None,
        max_news: int = 15,
        max_reports: int = 5,
        max_filings: int = 5,
        days_back: int = 90,
    ) -> str:
        """综合查询所有数据源，编译为研究简报（Markdown 格式）"""
        return self.compile_brief_v4(
            topic=topic, keywords=keywords, max_news=max_news,
            max_reports=max_reports, max_filings=max_filings, days_back=days_back,
        )

    def compile_brief_v4(
        self,
        topic: str,
        keywords: Optional[List[str]] = None,
        max_news: int = 15,
        max_reports: int = 5,
        max_filings: int = 5,
        days_back: int = 90,
        include_companies: bool = True,
        include_13f: bool = True,
        include_sources: bool = True,
        include_macro: bool = True,
        include_market: bool = True,
        topic_category=None,
    ) -> str:
        """v4.0 增强版研究简报 — 覆盖 10+ 个本地数据库

        Args:
            topic: 研究主题
            keywords: 关键词列表（为空时从 topic 中提取）
            max_news: 最大新闻数量
            max_reports: 最大研报数量
            max_filings: 最大 SEC 文件数量
            days_back: 新闻时间窗口（天）
            include_companies: 是否包含公司基本面
            include_13f: 是否包含 13F 机构持仓
            include_sources: 是否包含数据源可信度
            include_macro: 是否包含宏观经济数据
            include_market: 是否包含市场情报
            topic_category: TopicCategory 枚举（非金融主题自动跳过金融数据）

        Returns:
            Markdown 格式研究简报
        """
        # 非金融主题：按分类特定数据源标记控制
        # 使用 topic_config 中的分类特定数据源标记
        if topic_category is not None:
            try:
                from analysis.mirofish.topic_config import (
                    CRYPTO_BLOCKCHAIN_DATA_FLAGS,
                    REAL_ESTATE_DATA_FLAGS,
                    COMMODITIES_DATA_FLAGS,
                    MACRO_STRATEGY_DATA_FLAGS,
                    SOCIAL_OBSERVATION_DATA_FLAGS,
                    NON_FINANCIAL_DATA_FLAGS,
                    TopicCategory,
                )
                flag_map = {
                    TopicCategory.CRYPTO_BLOCKCHAIN: CRYPTO_BLOCKCHAIN_DATA_FLAGS,
                    TopicCategory.REAL_ESTATE: REAL_ESTATE_DATA_FLAGS,
                    TopicCategory.COMMODITIES: COMMODITIES_DATA_FLAGS,
                    TopicCategory.MACRO_STRATEGY: MACRO_STRATEGY_DATA_FLAGS,
                    TopicCategory.SOCIAL_OBSERVATION: SOCIAL_OBSERVATION_DATA_FLAGS,
                }
                flags = flag_map.get(topic_category, NON_FINANCIAL_DATA_FLAGS)
                include_macro = flags.get("use_fred", include_macro)
                include_market = flags.get("use_volatility", include_market)
                include_companies = flags.get("use_company", include_companies)
                include_13f = flags.get("use_13f", include_13f)
            except ImportError:
                # 回退到旧逻辑
                cat_str = str(topic_category).lower()
                is_financial = 'financial' in cat_str
                if not is_financial:
                    include_macro = False
                    include_market = False
                    include_companies = False
                    include_13f = False
        if not keywords:
            # 简单关键词提取：英文单词 + 中文词汇
            import re
            keywords = re.findall(r'[A-Za-z\u4e00-\u9fff]{2,}', topic)
            keywords = keywords[:10]

        query_str = " OR ".join(keywords)
        sections = []

        # 1. 研究主题
        sections.append(f"# 研究简报: {topic}")
        sections.append(f"\n**生成时间**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        sections.append(f"**关键词**: {', '.join(keywords)}")
        sections.append(f"**数据时间窗口**: 最近 {days_back} 天")

        # 1.5 宏观经济数据 (v4.1 新增)
        if include_macro:
            sections.append("\n## 宏观经济快照\n")
            try:
                key_fred = [
                    "CPIAUCSL", "CPILFESL", "PCEPILFE", "UNRATE", "FEDFUNDS",
                    "DGS10", "DFII10", "T10Y2Y", "M2SL", "WALCL", "RRPONTSYD",
                    "STLFSI4", "BAMLH0A0HYM2", "GDP", "INDPRO", "PAYEMS",
                    "UMCSENT", "CSUSHPISA", "MORTGAGE30US",
                    # 中国宏观系列
                    "CPALTT01CNM659N",  # 中国 CPI
                    "QCNN368BIS",       # BIS 中国房价
                    "IR3TIB01CNM156N",  # 中国 3M 同业利率
                    "XTNTVA01CNM664S",  # 中国贸易差额
                    "MANMM101CNM189N",  # 中国 M1
                    "EXCHUS",           # 美元/人民币
                ]
                fred_text = self.get_fred_summary(key_fred)
                sections.append(fred_text)
            except Exception as e:
                logger.error(f"get_fred_summary failed: {e}")

            try:
                sections.append(f"\n{self.get_valuation_metrics()}")
            except Exception as e:
                logger.error(f"get_valuation_metrics failed: {e}")

            try:
                sections.append(f"\n{self.get_credit_markets()}")
            except Exception as e:
                logger.error(f"get_credit_markets failed: {e}")

            try:
                sections.append(f"\n{self.get_energy_data()}")
            except Exception as e:
                logger.error(f"get_energy_data failed: {e}")

        # 1.6 市场情报 (v4.1 新增)
        if include_market:
            sections.append("\n## 市场情报\n")
            try:
                sections.append(self.get_market_overview_brief())
            except Exception as e:
                logger.error(f"get_market_overview_brief failed: {e}")

        # 2. 新闻
        sections.append("\n## 相关新闻\n")
        try:
            news_items = self.search_news(
                query_str, limit=max_news, days_back=days_back
            )
            if news_items:
                for item in news_items:
                    sections.append(f"- {item.summary()}")
            else:
                sections.append(f"_未找到近期相关新闻_")
        except Exception as e:
            sections.append(f"_新闻查询失败: {e}_")
            logger.error(f"search_news failed: {e}")

        # 3. 股票代码搜索
        import re
        symbols = re.findall(r'\b[A-Z]{1,5}\b', topic)
        if symbols:
            sections.append("\n## 按股票代码搜索\n")
            try:
                symbol_news = self.search_news_by_symbols(
                    symbols, limit=max_news, days_back=days_back
                )
                if symbol_news:
                    for item in symbol_news:
                        sections.append(f"- {item.summary()}")
                else:
                    sections.append(f"_未找到 {', '.join(symbols)} 相关新闻_")
            except Exception as e:
                logger.error(f"search_news_by_symbols failed: {e}")

        # 4. 研究报告
        sections.append("\n## 研究报告\n")
        try:
            reports = self.search_research_reports(
                keywords[0] if keywords else topic, limit=max_reports
            )
            if reports:
                for r in reports:
                    sections.append(f"- {r.summary()}")
            else:
                sections.append("_未找到相关研究报告_")
        except Exception as e:
            logger.error(f"search_research_reports failed: {e}")

        # 5. SEC Filings
        if symbols:
            sections.append("\n## SEC 文件\n")
            try:
                for sym in symbols[:3]:  # 最多查 3 个
                    filings = self.search_sec_filings(sym, limit=max_filings)
                    if filings:
                        sections.append(f"### {sym}")
                        for f in filings:
                            sections.append(f"- {f.summary()}")
            except Exception as e:
                logger.error(f"search_sec_filings failed: {e}")

        # 6. 重要人物
        sections.append("\n## 相关人物\n")
        try:
            for kw in keywords[:5]:
                persons = self.find_persons(kw, limit=3)
                if persons:
                    sections.append(f"### 与 '{kw}' 相关")
                    for p in persons:
                        sections.append(f"- {p.summary()}")
        except Exception as e:
            logger.error(f"find_persons failed: {e}")

        # 7. 市场数据
        if symbols:
            sections.append("\n## 市场数据（最近 30 天）\n")
            try:
                market = self.get_market_data(symbols, days=30)
                for sym, points in market.items():
                    if points:
                        latest = points[0]
                        sections.append(
                            f"- **{sym}**: 最新收盘价 {latest.close} "
                            f"({latest.date})"
                        )
                    else:
                        sections.append(f"- **{sym}**: 无市场数据")
            except Exception as e:
                logger.error(f"get_market_data failed: {e}")

        # 8. 公司基本面 (v4 新增)
        if symbols and include_companies:
            sections.append("\n## 公司基本面\n")
            for sym in symbols[:5]:
                try:
                    brief = self.get_company_financials_brief(sym)
                    sections.append(brief)
                except Exception as e:
                    logger.error(f"get_company_financials failed: {sym}: {e}")

        # 9. 13F 机构持仓 (v4 新增)
        if symbols and include_13f:
            sections.append("\n## 13F 机构持仓\n")
            for sym in symbols[:5]:
                try:
                    brief = self.get_13f_brief(sym)
                    sections.append(brief)
                except Exception as e:
                    logger.error(f"get_13f failed: {sym}: {e}")

        # 10. LiveNews 实时新闻 (v4.2 新增)
        sections.append("\n## LiveNews 实时快讯\n")
        try:
            ln_news = self.search_livenews(query_str, limit=min(max_news, 10), days_back=min(days_back, 7))
            if ln_news:
                for item in ln_news:
                    title = item.get("title", "") or item.get("content", "")[:120]
                    content = (item.get("content") or "")[:200]
                    source = item.get("source", "")
                    published = item.get("published_at", 0)
                    if published > 0:
                        pub_str = datetime.fromtimestamp(published / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
                    else:
                        pub_str = "N/A"
                    imp = item.get("importance", 0)
                    sections.append(f"- [{pub_str}] [{source}] {title[:150]} (imp={imp})")
                    if content and content != title:
                        sections.append(f"  {content[:180]}")
            else:
                sections.append("_未找到相关 LiveNews 快讯_")
        except Exception as e:
            sections.append(f"_LiveNews 查询失败: {e}_")
            logger.error(f"LiveNews query failed: {e}")

        # 11. 数据源可信度 (v4 新增)
        if include_sources:
            sections.append("\n## 数据来源概览\n")
            try:
                sources = self.get_source_credibility()
                by_category = {}
                for s in sources:
                    cat = s.get("category", "other")
                    by_category.setdefault(cat, []).append(s)
                for cat, srcs in sorted(by_category.items()):
                    sections.append(f"- **{cat}**: {len(srcs)} 个来源 (数据量: {sum(s.get('total_fetched', 0) for s in srcs):,})")
            except Exception as e:
                logger.error(f"get_source_credibility failed: {e}")

        sections.append("\n---\n*本简报由 ResearchQueries v4.2 自动生成 — 覆盖 11 个本地数据库 (700万+ 行数据)*")

        return "\n".join(sections)

    def __repr__(self) -> str:
        return (
            f"ResearchQueries(evidence_dir={self.evidence_dir}, "
            f"cache_size={len(self._cache._cache)})"
        )
