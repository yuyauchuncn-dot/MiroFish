#!/usr/bin/env python3
"""研究查询调度器 — 辩论引擎按需数据获取

核心理念: 代理在辩论过程中通过 <QUERY> 标签触发实时 DB 查询，
而非仅依赖预编译的研究简报。

查询格式: <QUERY>type: arg</QUERY>

支持的查询类型:
| 类型 | 示例 | 说明 |
|------|------|------|
| fred | CPIAUCSL | FRED 宏观数据 |
| valuation | — | S&P 500 PE/CAPE |
| energy | — | EIA 能源数据 |
| credit | — | 信贷市场 (TED, HY/IG 利差) |
| volatility | — | 波动率表面 (VIX, VVIX, SKEW) |
| yield | — | 国债收益率曲线 |
| cross_asset | — | 跨资产价格 |
| options | SPY | 期权 P/C Ratio |
| company | NVDA | 公司基本面 |
| 13f | Berkshire | 13F 机构持仓 |
| sec | Apple | SEC 文件内容 |
| person | 黄仁勋 | 人物新闻 + 社交帖子 |
| source | wallstreetcn | 来源可信度 |
| news | AI 芯片 | 新闻 FTS 搜索 |
| livenews | AI 芯片 | LiveNews 实时快讯 (14.7万+ 条) |
"""

import logging
import re
from typing import Callable, Optional

logger = logging.getLogger(__name__)


# ── 查询注册表 ─────────────────────────────────────────────────

_QUERY_REGISTRY = {}


def register_query(query_type: str, description: str = ""):
    """注册查询类型"""
    def decorator(func):
        _QUERY_REGISTRY[query_type] = {
            "func": func,
            "description": description,
        }
        return func
    return decorator


# ── 查询实现 ──────────────────────────────────────────────────

@register_query("fred", "FRED 宏观数据 (CPIAUCSL, UNRATE, DGS10 等)")
def _query_fred(arg: str, queries) -> str:
    series_id = arg.strip().upper()
    data = queries.get_fred_series(series_id, limit=6)
    if not data:
        return f"[FRED] 未找到系列: {series_id}"
    lines = [f"### FRED: {series_id}"]
    for row in data:
        lines.append(f"- {row['date']}: {row['value']:.2f}")
    return "\n".join(lines)


@register_query("valuation", "S&P 500 估值指标 (PE/CAPE/ERP)")
def _query_valuation(arg: str, queries) -> str:
    return queries.get_valuation_metrics(limit=8)


@register_query("energy", "EIA 能源数据 (原油/天然气/煤炭)")
def _query_energy(arg: str, queries) -> str:
    return queries.get_energy_data(limit=6)


@register_query("credit", "信贷市场 (TED, HY/IG 利差, 金融压力)")
def _query_credit(arg: str, queries) -> str:
    return queries.get_credit_markets(limit=5)


@register_query("volatility", "波动率表面 (VIX, VVIX, SKEW, MOVE)")
def _query_volatility(arg: str, queries) -> str:
    return queries.get_volatility_surface(limit=5)


@register_query("yield", "国债收益率曲线")
def _query_yield(arg: str, queries) -> str:
    return queries.get_yield_curve(limit=5)


@register_query("cross_asset", "跨资产价格 (黄金/白银/原油/BTC/DXY)")
def _query_cross_asset(arg: str, queries) -> str:
    return queries.get_cross_asset_summary(limit=5)


@register_query("options", "期权 P/C Ratio")
def _query_options(arg: str, queries) -> str:
    tickers = [t.strip() for t in arg.split(",")] if arg else ["SPY", "SP500_AGG"]
    return queries.get_put_call_ratio(tickers=tickers, limit=5)


@register_query("company", "公司基本面 (财务指标/估值)")
def _query_company(arg: str, queries) -> str:
    symbol = arg.strip().upper()
    return queries.get_company_financials_brief(symbol)


@register_query("13f", "13F 机构持仓")
def _query_13f(arg: str, queries) -> str:
    return queries.get_13f_brief(arg.strip())


@register_query("sec", "SEC 文件内容")
def _query_sec(arg: str, queries) -> str:
    results = queries.get_sec_filing_content(arg.strip(), limit=3)
    if not results:
        return f"[SEC] 未找到 '{arg.strip()}' 的文件"
    lines = [f"### SEC 文件: {arg.strip()}"]
    for r in results:
        lines.append(f"- **{r.get('filing_type', 'N/A')}** ({r.get('filing_date', 'N/A')})")
        content = r.get("content", "")
        if content:
            lines.append(f"  {content[:300]}")
    return "\n".join(lines)


@register_query("person", "人物新闻 + 社交帖子")
def _query_person(arg: str, queries) -> str:
    name = arg.strip()
    news = queries.search_news(name, limit=5)
    posts = queries.get_person_social_posts(name, limit=5)
    lines = [f"### 人物: {name}"]
    if news:
        lines.append(f"\n**相关新闻** ({len(news)} 条):")
        for n in news:
            title = getattr(n, "title", "")
            imp = getattr(n, "importance", 0)
            pub = getattr(n, "published_at", "")
            if isinstance(pub, (int, float)) and pub > 0:
                from datetime import datetime
                pub_str = datetime.fromtimestamp(pub/1000).strftime("%Y-%m-%d")
            else:
                pub_str = str(pub)
            lines.append(f"- [{pub_str}] {title[:100]} (importance={imp})")
    if posts:
        lines.append(f"\n**社交帖子** ({len(posts)} 条):")
        for p in posts:
            if hasattr(p, "get"):
                lines.append(f"- [{p.get('created_at', '')}] {p.get('content', '')[:100]}")
            else:
                content = getattr(p, "content", str(p))[:100]
                created = getattr(p, "created_at", "")
                lines.append(f"- [{created}] {content}")
    return "\n".join(lines) if (news or posts) else f"[人物] 未找到 '{name}' 的内容"


@register_query("source", "来源可信度")
def _query_source(arg: str, queries) -> str:
    return queries.get_source_credibility_brief(arg.strip())


@register_query("news", "新闻 FTS 搜索")
def _query_news(arg: str, queries) -> str:
    results = queries.search_news(arg.strip(), limit=8)
    if not results:
        return f"[新闻] 未找到关于 '{arg.strip()}' 的新闻"
    lines = [f"### 新闻: {arg.strip()}"]
    for n in results:
        pub = getattr(n, "published_at", "")
        title = getattr(n, "title", "")
        imp = getattr(n, "importance", 0)
        if isinstance(pub, (int, float)) and pub > 0:
            from datetime import datetime
            pub_str = datetime.fromtimestamp(pub/1000).strftime("%Y-%m-%d")
        else:
            pub_str = str(pub)
        lines.append(f"- [{pub_str}] {title[:150]} (importance={imp})")
    return "\n".join(lines)


@register_query("livenews", "LiveNews 实时快讯 (FTS5 搜索)")
def _query_livenews(arg: str, queries) -> str:
    results = queries.search_livenews(arg.strip(), limit=10, days_back=7)
    if not results:
        return f"[LiveNews] 未找到关于 '{arg.strip()}' 的实时快讯"
    lines = [f"### LiveNews 实时快讯: {arg.strip()}"]
    from datetime import datetime
    for item in results:
        title = item.get("title", "") or item.get("content", "")[:120]
        source = item.get("source", "")
        pub = item.get("published_at", 0)
        pub_str = datetime.fromtimestamp(pub / 1000).strftime("%Y-%m-%d %H:%M") if pub > 0 else "N/A"
        imp = item.get("importance", 0)
        lines.append(f"- [{pub_str}] [{source}] {title[:150]} (imp={imp})")
    return "\n".join(lines)


# ── 类型映射与建议 ────────────────────────────────────────────

# 自创类型 → 有效类型的映射
_TYPE_ALIASES = {
    # 代理常自创的复合类型
    "market_data": "cross_asset",
    "market_macro": "fred",
    "macro": "fred",
    "market": "cross_asset",
    "liquidity": "credit",
    "liquidity_sentiment": "credit",
    "sentiment": "news",
    "options_positioning": "options",
    "options_positioning_and_sector_capex_roic": "options",
    "capex": "company",
    "sector": "company",
    "commodity": "cross_asset",
    "oil": "energy",
    "gold": "cross_asset",
    "bond": "yield",
    "rates": "fred",
    "inflation": "fred",
    "risk": "volatility",
    "default": "credit",
    "leverage": "credit",
    "policy": "news",
    "industrial_policy": "news",
    # 在线搜索别名
    "web": "tavily",
    "online": "tavily",
    "search": "tavily",
    "google": "tavily",
    "internet": "tavily",
    # 中国宏观别名
    "china": "fred",
    "china_macro": "fred",
    "cn_macro": "fred",
    "cn_housing": "fred",
    "cn_rates": "fred",
    "cn_trade": "fred",
    "cn_equity": "fred",
    "cn_credit": "fred",
}


def _map_type(invented_type: str) -> str:
    """将自创类型映射到有效类型

    Args:
        invented_type: 代理自创的类型名

    Returns:
        有效类型名，或空字符串（如果无法映射）
    """
    invented = invented_type.lower().strip()

    # 精确匹配别名表
    if invented in _TYPE_ALIASES:
        return _TYPE_ALIASES[invented]

    # 前缀/包含匹配
    for alias, valid in _TYPE_ALIASES.items():
        if alias in invented or invented in alias:
            return valid

    # 直接检查是否已为有效类型
    if invented in _QUERY_REGISTRY:
        return invented

    return ""


def _suggest_type(query_type: str) -> list:
    """基于关键词建议有效类型

    Args:
        query_type: 未知类型名

    Returns:
        最多 3 个建议类型
    """
    suggestions = set()
    query_lower = query_type.lower()

    # 关键词 → 类型映射
    keyword_map = {
        ("price", "asset", "gold", "silver", "oil", "btc", "dxy", "crypto"): "cross_asset",
        ("cpi", "pce", "gdp", "unemployment", "rate", "inflation", "treasury", "fed"): "fred",
        ("credit", "spread", "yield", "default", "bond"): "credit",
        ("volatility", "vix", "risk", "move"): "volatility",
        ("option", "put", "call", "gamma"): "options",
        ("company", "financial", "earnings", "revenue", "capex", "roic"): "company",
        ("13f", "holding", "institution", "portfolio", "berkshire"): "13f",
        ("sec", "filing", "10-k", "10-q"): "sec",
        ("person", "social", "post", "tweet"): "person",
        ("news", "headline", "event", "policy"): "news",
        ("energy", "oil", "crude", "gas", "coal"): "energy",
        ("valuation", "pe", "cape", "erp"): "valuation",
        ("web", "online", "search", "latest", "current", "real-time"): "tavily",
        ("china", "cn", "chinese", "shanghai", "csi", "hang seng", "a-share", "a股", "中国"): "fred",
        ("china housing", "cn housing", "房价", "房地产", "property price"): "tavily",
        ("china pmi", "cn pmi", "中国pmi"): "tavily",
        ("china gdp", "cn gdp", "中国gdp"): "tavily",
        ("social financing", "社融", "tsf"): "tavily",
    }

    for keywords, qtype in keyword_map.items():
        if any(kw in query_lower for kw in keywords):
            suggestions.add(qtype)
        if query_lower in keywords:
            suggestions.add(qtype)

    return sorted(suggestions)[:3]


# ── 调度器 ────────────────────────────────────────────────────

class QueryDispatcher:
    """按需查询调度器

    用法:
        dispatcher = QueryDispatcher(queries)
        result = dispatcher.execute("fred: CPIAUCSL")
    """

    # 正则: 匹配 <QUERY>type: arg</QUERY>
    QUERY_PATTERN = re.compile(r"<QUERY>\s*([^<]+?)\s*</QUERY>", re.IGNORECASE)

    def __init__(self, queries, tavily_client=None, tavily_max_results=3):
        """
        Args:
            queries: ResearchQueries 实例
            tavily_client: TavilyClient 实例（可选，用于在线搜索）
            tavily_max_results: Tavily 每次搜索返回的最大结果数
        """
        self.queries = queries
        self.query_count = 0
        self.query_log = []  # 记录所有查询用于审计
        self._tavily_client = tavily_client
        self._tavily_max_results = tavily_max_results
        self._tavily_cache = {}  # 简单会话级缓存

    def execute(self, query_text: str) -> str:
        """执行单条查询

        Args:
            query_text: "type: arg" 格式

        Returns:
            查询结果文本，或错误信息
        """
        query_text = query_text.strip()
        if not query_text:
            return "[查询错误] 查询文本为空"

        # ── 修复 1: 检测并纠正 template 格式 ──
        # 常见错误: "type: market_data arg: wti_crude_price"
        # 应改为: "cross_asset: wti_crude_price"
        template_pattern = re.compile(r"^type:\s*(\S+)\s+arg:\s*(.+)$", re.IGNORECASE)
        m = template_pattern.match(query_text)
        if m:
            invented_type = m.group(1).strip().lower()
            arg = m.group(2).strip()
            # 尝试将自创类型映射到有效类型
            query_type = _map_type(invented_type)
            if query_type:
                logger.debug(f"  [ODQ] 修正模板格式: type:{invented_type} → {query_type}")
            else:
                self.query_count += 1
                suggestions = _suggest_type(invented_type)
                suggestion_text = f"。你可能想用的是: {', '.join(suggestions)}" if suggestions else ""
                return f"[查询错误] 未知类型 '{invented_type}'{suggestion_text}"
        elif query_text.lower().startswith("type:"):
            # 仅有 type: 部分，缺少 arg: — 用自创类型推断有效类型，空参数执行
            invented_type = query_text[5:].strip().lower()
            query_type = _map_type(invented_type)
            if query_type:
                logger.debug(f"  [ODQ] 修正缺失 arg 格式: type:{invented_type} → {query_type}(空参)")
                arg = ""  # 使用空参数，让查询返回默认值
            else:
                self.query_count += 1
                suggestions = _suggest_type(invented_type)
                suggestion_text = f"。你可能想用的是: {', '.join(suggestions)}" if suggestions else ""
                return f"[查询错误] 未知类型 '{invented_type}'{suggestion_text}"
        elif ":" not in query_text:
            # 代理写了 bare 类型名（无冒号无参数），如 "credit"
            # 尝试映射为有效类型，用空参数执行
            mapped = _map_type(query_text.strip().lower())
            if mapped:
                query_type = mapped
                arg = ""
                logger.debug(f"  [ODQ] 修正 bare 类型: {query_text} → {mapped}(空参)")
            else:
                suggestions = _suggest_type(query_text.strip().lower())
                suggestion_text = f"。你可能想用的是: {', '.join(suggestions)}" if suggestions else ""
                available = ", ".join(sorted(_QUERY_REGISTRY.keys()))
                self.query_count += 1
                return f"[查询错误] 未知类型 '{query_text}'{suggestion_text}。可用: {available}"
        else:
            query_type, arg = query_text.split(":", 1)
            query_type = query_type.strip().lower()
            arg = arg.strip()

            # ── 修复 2: 自创类型模糊映射 ──
            if query_type not in _QUERY_REGISTRY and query_type != "tavily":
                mapped = _map_type(query_type)
                if mapped:
                    logger.debug(f"  [ODQ] 映射类型: {query_type} → {mapped}")
                    query_type = mapped
                else:
                    self.query_count += 1
                    suggestions = _suggest_type(query_type)
                    suggestion_text = f"。你可能想用的是: {', '.join(suggestions)}" if suggestions else ""
                    available = ", ".join(sorted(_QUERY_REGISTRY.keys()))
                    return f"[查询错误] 未知类型 '{query_type}'{suggestion_text}。可用: {available}"

        # ── 特殊处理: tavily 在线搜索（不走本地 DB 注册表）──
        if query_type == "tavily":
            return self._execute_tavily(arg)

        self.query_count += 1

        try:
            func = _QUERY_REGISTRY[query_type]["func"]
            result = func(arg, self.queries)
            self.query_log.append({
                "type": query_type,
                "arg": arg,
                "status": "ok",
                "chars": len(result),
            })
            logger.debug(f"  [ODQ #{self.query_count}] {query_type}: {arg} → {len(result)} 字符")
            return result
        except Exception as e:
            self.query_log.append({
                "type": query_type,
                "arg": arg,
                "status": "error",
                "error": str(e),
            })
            logger.warning(f"  [ODQ #{self.query_count}] {query_type}: {arg} → 错误: {e}")
            return f"[查询错误] {query_type}: {arg} — {e}"

    def _execute_tavily(self, search_query: str) -> str:
        """执行 Tavily 在线搜索

        结果标记为 [在线搜索, 需交叉验证] 以区别于本地 DB 数据。
        """
        self.query_count += 1

        if not self._tavily_client:
            return "[在线搜索] Tavily 未配置（缺少 TAVILY_API_KEY），无法执行在线搜索"

        cache_key = search_query.strip().lower()
        if cache_key in self._tavily_cache:
            logger.debug(f"  [ODQ] Tavily 缓存命中: {search_query}")
            result = self._tavily_cache[cache_key]
            self.query_log.append({"type": "tavily", "arg": search_query, "status": "ok (cache)", "chars": len(result)})
            return result

        try:
            response = self._tavily_client.search(
                query=search_query.strip(),
                max_results=self._tavily_max_results,
                include_answer=True,
            )
            lines = [f"### Tavily 在线搜索 [在线搜索, 需交叉验证]: {search_query.strip()}"]
            answer = response.get("answer", "")
            if answer:
                lines.append(f"\n**搜索摘要**: {answer}")

            lines.append("\n**相关新闻源**:")
            for i, r in enumerate(response.get("results", [])[:5], 1):
                title = r.get("title", "N/A")
                snippet = (r.get("snippet") or "N/A")[:200]
                url = r.get("url", "N/A")
                source = r.get("source", "N/A")
                lines.append(f"{i}. **{title}** [{source}]")
                lines.append(f"   {snippet}")
                lines.append(f"   链接: {url}")

            result = "\n".join(lines)
            self._tavily_cache[cache_key] = result
            self.query_log.append({"type": "tavily", "arg": search_query, "status": "ok", "chars": len(result)})
            logger.info(f"  [ODQ] Tavily 搜索: {search_query[:50]} → {len(result)} 字符")
            return result
        except Exception as e:
            logger.warning(f"  [ODQ] Tavily 搜索失败: {search_query} — {e}")
            self.query_log.append({"type": "tavily", "arg": search_query, "status": "error", "error": str(e)})
            return f"[在线搜索失败] Tavily 查询 '{search_query}' 出错: {e}"

    def extract_and_execute(self, text: str) -> dict:
        """从文本中提取所有 <QUERY> 标签并执行

        Args:
            text: LLM 响应文本（可能包含 <QUERY> 标签）

        Returns:
            {"queries": [(type, arg, result), ...], "clean_text": str}
        """
        matches = self.QUERY_PATTERN.findall(text)
        if not matches:
            return {"queries": [], "clean_text": text}

        results = []
        for match in matches:
            result_text = self.execute(match)
            query_type = match.split(":", 1)[0].strip().lower() if ":" in match else match.strip()
            arg = match.split(":", 1)[1].strip() if ":" in match else ""
            results.append((query_type, arg, result_text))

        # 清理文本中的 <QUERY> 标签
        clean_text = self.QUERY_PATTERN.sub("", text).strip()

        logger.info(f"  [ODQ] 从响应中提取 {len(results)} 条按需查询")
        return {"queries": results, "clean_text": clean_text}

    def build_injection_block(self, query_results: list) -> str:
        """构建数据注入块，添加到研究简报"""
        if not query_results:
            return ""

        lines = ["\n## 辩论期间按需查询结果"]
        for query_type, arg, result in query_results:
            lines.append(f"\n### 按需查询: {query_type}: {arg}")
            lines.append(result)
        lines.append("")
        return "\n".join(lines)

    def get_available_types(self) -> str:
        """返回可用查询类型列表（用于 system prompt）"""
        lines = ["## 按需数据查询"]
        lines.append("重要：必须严格按照以下格式使用，不要自创类型或格式！")
        lines.append("格式: `<QUERY>类型: 参数</QUERY>")
        lines.append("注意：`类型` 必须是以下列表中的一个，`参数` 是具体的查询内容\n")
        lines.append("### 可用查询类型及示例")
        examples = [
            ("fred", "CPIAUCSL", "FRED 宏观指标 (CPI/失业率/GDP 等)"),
            ("valuation", "", "S&P 500 PE/CAPE/ERP 估值"),
            ("energy", "", "EIA 能源数据 (原油产量/库存/SPR)"),
            ("credit", "", "信贷市场 (TED/HY利差/IG利差/金融压力)"),
            ("volatility", "", "波动率表面 (VIX/VVIX/SKEW/MOVE)"),
            ("yield", "", "国债收益率曲线 (3M-30Y)"),
            ("cross_asset", "", "跨资产价格 (黄金/白银/原油/BTC/DXY)"),
            ("options", "SPY", "期权 P/C Ratio (默认 SPY,SP500_AGG)"),
            ("company", "NVDA", "公司基本面 (股票代码)"),
            ("13f", "Berkshire", "13F 机构持仓 (经理名或股票)"),
            ("sec", "Apple", "SEC 文件内容 (公司名)"),
            ("person", "黄仁勋", "人物新闻和社交帖子"),
            ("source", "wallstreetcn", "来源可信度"),
            ("news", "AI芯片", "新闻 FTS 搜索"),
            ("livenews", "AI芯片", "LiveNews 实时快讯 (最近 7 天)"),
            ("tavily", "中国房价指数 2026", "Tavily 在线搜索 (实时网络数据)"),
            ("fred", "CPALTT01CNM659N", "中国 CPI"),
            ("fred", "QCNN368BIS", "中国房价指数 (BIS)"),
            ("fred", "IR3TIB01CNM156N", "中国 3M 同业利率"),
            ("tavily", "中国70城房价指数最新", "NBS 70城房价 (网络搜索)"),
            ("tavily", "中国社融存量 2026年3月", "中国社融/PMI/GDP (网络搜索)"),
        ]
        for qtype, example, desc in examples:
            if example:
                lines.append(f"- `<QUERY>{qtype}: {example}</QUERY>` → {desc}")
            else:
                lines.append(f"- `<QUERY>{qtype}</QUERY>` → {desc}")
        lines.append("\n错误示例 (不要这样做):")
        lines.append("- ❌ `<QUERY>type: market_data arg: xxx</QUERY>` — 不要使用 type/arg 占位符")
        lines.append("- ❌ `<QUERY>market_data: xxx</QUERY>` — market_data 不是有效类型，用 cross_asset")
        lines.append("- ❌ `<QUERY>liquidity_sentiment: xxx</QUERY>` — 不是有效类型，用 fred 或 credit")
        return "\n".join(lines)
