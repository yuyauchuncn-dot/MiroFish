#!/usr/bin/env python3
"""MiroFish v4 报告生成器 — 多代理辩论 + 预测引擎

从 transcript 生成 v4 报告的完整流程:
1. compile_brief_v4() 聚合 8 个本地 DB
2. DebateEngine 运行多代理辩论
3. 基于辩论结果生成情景预测
4. 写入 PredictionStore
5. 生成 v4 格式 Markdown 报告
"""

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── 加载 monorepo .env（BAILIAN_API_KEY, TAVILY_API_KEY 等）────────
def _load_env() -> None:
    """自动加载 monorepo 根目录的 .env 文件"""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return  # python-dotenv 未安装时静默跳过
    # 向上找到 monorepo 根目录
    p = Path(__file__).resolve()
    for _ in range(8):
        env_file = p / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=False)  # 不覆盖已存在的环境变量
            return
        p = p.parent

_load_env()
logger = logging.getLogger(__name__)

# ── 路径 ─────────────────────────────────────────────────────────
# 此文件在 src/v4/ 下，需要找到 monorepo root
def _find_mono_root() -> Path:
    """从当前文件位置向上查找 monorepo root (包含 monodata/ 目录的层级)"""
    import os
    env_root = os.environ.get("MONO_ROOT")
    if env_root:
        return Path(env_root).resolve()
    p = Path(__file__).resolve()
    for _ in range(8):
        if (p / "monodata").exists() and (p / "mirofish").exists():
            return p
        p = p.parent
    # Fallback: v4_generator.py → v4/ → src/ → mirofish/ → monorepo root (4 levels up)
    return Path(__file__).resolve().parent.parent.parent.parent

_MONO_ROOT = _find_mono_root()
_SPEC_PATH = Path(__file__).parent / "mirofish_v4_spec.md"


def _call_bailian(messages: list, model: str = "qwen3.6-plus",
                  temperature: float = 0.7, max_tokens: int = 8192) -> str:
    """调用百炼 Qwen LLM

    Args:
        messages: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
        model: 模型名称
        temperature: 温度参数
        max_tokens: 最大 token 数

    Returns:
        LLM 回复文本
    """
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai 库未安装")
        return ""

    api_key = os.environ.get("BAILIAN_API_KEY", "")
    use_openai_fallback = False

    if not api_key:
        # Fallback to OpenAI if BAILIAN_API_KEY is not set
        openai_key = os.environ.get("OPENAI_API_KEY", "")
        if openai_key:
            logger.info("BAILIAN_API_KEY 未设置，使用 OpenAI fallback")
            use_openai_fallback = True
            api_key = openai_key
        else:
            logger.error("BAILIAN_API_KEY 和 OPENAI_API_KEY 均未设置")
            return ""

    if use_openai_fallback:
        base_url = "https://api.openai.com/v1"
        model = "gpt-4.1"
    else:
        base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"百炼 LLM 调用失败: {e}")
        return ""


def _load_spec() -> str:
    """加载 v4 spec 文件"""
    if _SPEC_PATH.exists():
        return _SPEC_PATH.read_text(encoding="utf-8")
    return "MiroFish v4.0 规范文件未找到，使用默认格式"


def _extract_transcript_topic(transcript: str) -> str:
    """从字幕内容提取主题"""
    text_lower = transcript[:2000].lower()
    topics = {
        "美股": any(w in text_lower for w in ["美股", "标普", "sp500", "s&p"]),
        "加密货币": any(w in text_lower for w in ["crypto", "bitcoin", "btc", "eth", "加密"]),
        "人工智能": any(w in text_lower for w in ["ai", "人工智能", "nvidia", "nvda", "openai"]),
        "地缘政治": any(w in text_lower for w in ["地缘", "战争", "冲突", "制裁", "中东"]),
        "宏观经济": any(w in text_lower for w in ["宏观", "美联储", "fed", "利率", "通胀", "cpi"]),
        "黄金": any(w in text_lower for w in ["黄金", "gold", "贵金属"]),
        "能源": any(w in text_lower for w in ["能源", "石油", "oil", "天然气", "lng"]),
    }
    matched = [k for k, v in topics.items() if v]
    return "、".join(matched) if matched else "综合市场分析"


def _clean_transcript(transcript: str, max_chars: int = 15000) -> str:
    """清理字幕文本，保留核心内容"""
    text = re.sub(r'\d{2}:\d{2}[:：]\d{2}', '', transcript)
    text = re.sub(r'\n{3,}', '\n\n', text)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[... 内容截取，总长度 " + str(len(transcript)) + " 字符 ...]"
    return text.strip()


class V4Generator:
    """v4 报告生成器 — 多代理辩论 + 预测引擎

    实现统一接口: generate(transcript, title, ...) -> dict
    """

    def generate(
        self,
        transcript: str,
        title: str,
        video_id: str,
        channel: str = "Unknown",
        social_context: str = "",
        sentiment_context: str = "",
        tavily_data: Optional[dict] = None,
        force_topic: Optional[str] = None,
        force_topic_suffix: Optional[str] = None,
        **kwargs,
    ) -> Optional[dict]:
        """生成 v4 报告

        Args:
            transcript: 字幕内容
            title: 视频标题
            video_id: 视频 ID
            channel: 频道名称
            social_context: 社交媒体上下文
            sentiment_context: 情绪分析上下文
            tavily_data: Tavily 搜索结果
            force_topic: 强制使用指定主题分类（可选）
            force_topic_suffix: 文件名后缀（可选，用于避免覆盖已有报告）

        Returns:
            {"report_path": str, "report_content": str}
        """
        tavily_context = ""
        if tavily_data and tavily_data.get("results"):
            tavily_context = "\n".join(
                f"- {r.get('title', '')}: {(r.get('snippet') or '')[:200]}"
                for r in tavily_data["results"][:5]
                if (r.get('snippet') or r.get('title'))
            )

        result = generate_v4_report(
            video_id=video_id,
            title=title,
            transcript=transcript,
            channel=channel,
            social_context=social_context,
            sentiment_context=sentiment_context,
            tavily_context=tavily_context,
            tavily_data=tavily_data,
            force_topic=force_topic,
            force_topic_suffix=force_topic_suffix,
        )

        if not result:
            return None

        return {
            "report_path": result["report_path"],
            "report_content": result["report_content"],
        }


def generate_v4_report(
    video_id: str,
    title: str,
    transcript: str,
    channel: str = "Unknown",
    social_context: str = "",
    sentiment_context: str = "",
    tavily_context: str = "",
    tavily_data: Optional[dict] = None,
    force_topic: Optional[str] = None,
    force_topic_suffix: Optional[str] = None,
) -> Optional[dict]:
    """生成 v4 格式报告

    Args:
        video_id: 视频 ID
        title: 视频标题
        transcript: 字幕内容
        channel: 频道名称
        social_context: 社交媒体上下文 (可选)
        sentiment_context: 情绪分析上下文 (可选)
        tavily_context: Tavily 搜索结果 (可选)
        force_topic: 强制使用指定主题分类（可选），绕过自动分类器
            可选值: "financial"|"war_conflict"|"social_lifestyle"|"travel_nomad"|
                   "technology"|"crypto_blockchain"|"real_estate"|"commodities"|
                   "macro_strategy"|"social_observation"
        force_topic_suffix: 文件名后缀（可选），用于避免覆盖已有报告，如 "_commodities"

    Returns:
        {
            "report_path": str,
            "report_content": str,
            "predictions_count": int,
            "debate_rounds": int,
            "elapsed_seconds": float,
        }
    """
    start_time = time.time()

    # 1. 清理输入
    logger.info(f"[v4] 开始生成报告: {title[:60]}...")
    clean_text = _clean_transcript(transcript)

    # 1.5 主题分类（多主题支持 + 负向关键字 + 频道先验）
    domain_constraint = None
    final_agents = None
    final_tensions = None
    topic_display = "金融与投资分析"
    try:
        sys_path_backup = list(sys.path)
        sys.path.insert(0, str(_MONO_ROOT / "mirofish" / "src"))
        from v4.topic_config import classify_topic_v2, get_topic_config, TopicCategory
        from v4.dynamic_agents import (
            extract_entities, compose_dynamic_agents, compose_debate_team,
        )

        # 如果指定了 force_topic，直接使用该分类，跳过自动分类
        if force_topic:
            try:
                topic_category = TopicCategory(force_topic)
            except ValueError:
                valid = [c.value for c in TopicCategory]
                logger.warning(f"[v4] 无效的分类 '{force_topic}'，使用自动分类。可选值: {valid}")
                topic_category = None
        else:
            topic_category = None

        if topic_category is None:
            # 自动分类
            topic_result = classify_topic_v2(transcript, title, channel=channel)
            topic_category = topic_result.primary
            topic_display = topic_result.display_name
            logger.info(
                f"[v4] 自动分类: {topic_category.value} ({topic_display}) "
                f"置信度={topic_result.primary_score:.2f}"
            )
            if topic_result.secondary:
                logger.info(
                    f"[v4] 次分类: {topic_result.secondary.value} "
                    f"置信度={topic_result.secondary_score:.2f}"
                )
            domain_constraint = topic_result.domain_constraint
        else:
            # 强制分类
            topic_config_temp = get_topic_config(topic_category)
            topic_display = topic_config_temp.display_name
            logger.info(f"[v4] 强制分类: {topic_category.value} ({topic_display}) [force_topic]")

        topic_config = get_topic_config(topic_category)
        sys.path = sys_path_backup
    except Exception as e:
        logger.warning(f"[v4] 主题分类失败，使用默认金融主题: {e}")
        class _DummyConfig:
            display_name = "金融与投资分析"
            agents = None
            natural_tensions = None
            report_title = "深度投资分析报告"
            data_source_flags = None
            suggestion_fields = None
        topic_category = None
        topic_config = _DummyConfig()
        topic_display = "金融与投资分析"

    topic_label = topic_display if hasattr(topic_config, 'display_name') else "金融与投资分析"

    # 1.7 动态代理生成（实体提取 + 模板化组合 + 团队编排）
    if topic_category is not None and hasattr(topic_config, 'agents') and topic_config.agents:
        try:
            sys_path_backup = list(sys.path)
            sys.path.insert(0, str(_MONO_ROOT / "mirofish" / "src"))
            entities = extract_entities(clean_text, title, top_n=5)
            logger.info(f"[v4] 实体提取: {[e.name for e in entities[:3]]}")

            dynamic = compose_dynamic_agents(entities, topic_category, max_agents=2)
            if dynamic:
                logger.info(f"[v4] 动态代理: {[d.name for d in dynamic]}")

            final_agents, final_tensions = compose_debate_team(
                static_agents=topic_config.agents,
                dynamic_agents=dynamic,
                static_tensions=topic_config.natural_tensions,
                max_total_agents=8,
            )
            logger.info(f"[v4] 辩论团队: {len(final_agents)} 代理, {len(final_tensions)} 组张力")
            sys.path = sys_path_backup
        except Exception as e:
            logger.warning(f"[v4] 动态代理生成失败，使用静态代理: {e}")
            final_agents = topic_config.agents
            final_tensions = topic_config.natural_tensions

    # 2. 编译研究简报 (DB 聚合，按主题过滤)
    logger.info("[v4] 编译研究简报...")
    try:
        sys_path_backup = list(sys.path)
        sys.path.insert(0, str(_MONO_ROOT / "mirofish" / "src"))
        from utils.research_queries import ResearchQueries
        queries = ResearchQueries()
        research_brief = queries.compile_brief_v4(topic_label, topic_category=topic_category)
        sys.path = sys_path_backup
        logger.info(f"[v4] 研究简报: {len(research_brief)} 字符")
    except Exception as e:
        logger.warning(f"[v4] 研究简报编译失败，使用字幕替代: {e}")
        research_brief = clean_text[:5000]

    # 2.5 注入 Tavily 在线搜索数据到研究简报（辩论引擎可见）
    if tavily_data and tavily_data.get("results"):
        tavily_section = _build_tavily_brief_section(tavily_data)
        research_brief += "\n\n" + tavily_section
        logger.info(f"[v4] Tavily 数据已注入研究简报: +{len(tavily_section)} 字符")

    # 2.6 注入语义消歧约束（防止同义词误判）
    if domain_constraint:
        constraint_section = f"\n\n## ⚠️ 语义消歧提示（必须遵守）\n\n{domain_constraint}\n"
        research_brief = constraint_section + research_brief
        logger.info(f"[v4] 语义消歧约束已注入研究简报: +{len(constraint_section)} 字符")

    # 3. 运行多代理辩论
    logger.info("[v4] 运行多代理辩论...")
    try:
        sys_path_backup = list(sys.path)
        sys.path.insert(0, str(_MONO_ROOT / "mirofish" / "src"))
        from v4.debate_engine import DebateEngine
        from v4.prediction_store import PredictionStore, Prediction
        from utils.query_dispatcher import QueryDispatcher
        from utils.research_queries import ResearchQueries
        store = PredictionStore()
        engine = DebateEngine(store)

        # 初始化 Tavily 客户端（用于辩论中按需在线搜索）
        tavily_client = _init_tavily_client()
        if tavily_client:
            logger.info("[v4] Tavily 在线搜索已启用，代理可在辩论中触发实时网络查询")
        else:
            logger.debug("[v4] Tavily 未配置，辩论中无法执行在线搜索")

        # 创建按需查询调度器 (支持辩论中实时 DB + Tavily 查询)
        try:
            queries = ResearchQueries()
            query_dispatcher = QueryDispatcher(queries, tavily_client=tavily_client)
            qtypes = "15 种查询类型 (含 Tavily 在线搜索)" if tavily_client else "14 种本地查询类型"
            logger.info(f"[v4] 按需查询调度器已初始化，支持 {qtypes}")
        except Exception as e:
            logger.warning(f"[v4] 按需查询调度器初始化失败: {e}，辩论中无法实时查询 DB")
            query_dispatcher = None

        result = engine.run_debate(
            topic=f"{title} ({topic_label})",
            research_brief=research_brief,
            llm_call=lambda msgs: _call_bailian(msgs),
            report_id=f"v4_{video_id}_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
            query_dispatcher=query_dispatcher,
            agents=final_agents if final_agents is not None else getattr(topic_config, 'agents', None),
            natural_tensions=final_tensions if final_tensions is not None else getattr(topic_config, 'natural_tensions', None),
        )
        sys.path = sys_path_backup
        logger.info(f"[v4] 辩论完成: {len(result.records)} 代理，{len(result.predictions)} 条预测")
        if query_dispatcher:
            logger.info(f"[v4] 按需查询统计: {query_dispatcher.query_count} 次查询")
    except Exception as e:
        logger.error(f"[v4] 辩论引擎失败: {e}", exc_info=True)
        result = None

    # 4. 组装完整报告
    logger.info("[v4] 组装报告...")
    report_content = _assemble_v4_report(
        title=title,
        topic=topic_label,
        topic_config=topic_config,
        channel=channel,
        video_id=video_id,
        transcript=clean_text,
        research_brief=research_brief,
        debate_result=result,
        social_context=social_context,
        sentiment_context=sentiment_context,
        tavily_context=tavily_context,
    )

    # 5. 保存预测
    predictions_count = 0
    if result and result.predictions:
        try:
            store = PredictionStore()
            for pred in result.predictions:
                store.save(pred)
            predictions_count = len(result.predictions)
            logger.info(f"[v4] 已保存 {predictions_count} 条预测")
        except Exception as e:
            logger.warning(f"[v4] 预测保存失败: {e}")

    # 6. 保存报告文件
    date_str = datetime.now().strftime("%Y%m%d")
    safe_title = _sanitize_filename(title)
    # Use topic category as suffix for report filename (e.g., _macro_strategy)
    topic_suffix = f"_{topic_category.value}" if topic_category is not None and hasattr(topic_category, 'value') else ""
    suffix = force_topic_suffix or topic_suffix
    report_filename = f"{date_str}_{video_id}_{safe_title}_v4_MiroFish{suffix}.md"
    report_dir = _MONO_ROOT / "monodata" / "reports" / "youtube" / channel
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / report_filename

    report_path.write_text(report_content, encoding="utf-8")
    logger.info(f"[v4] 报告已保存: {report_path}")

    elapsed = time.time() - start_time
    debate_rounds = len(result.records) if result else 0

    return {
        "report_path": str(report_path),
        "report_content": report_content,
        "predictions_count": predictions_count,
        "debate_rounds": debate_rounds,
        "elapsed_seconds": elapsed,
    }


def _assemble_v4_report(
    title: str,
    topic: str,
    topic_config,
    channel: str,
    video_id: str,
    transcript: str,
    research_brief: str,
    debate_result,
    social_context: str,
    sentiment_context: str,
    tavily_context: str,
) -> str:
    """组装 v4 格式的 Markdown 报告（主题感知）"""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    lines = []

    # 标题
    report_title = getattr(topic_config, 'report_title', '深度投资分析报告')
    lines.append(f"# MiroFish v4.0 {report_title}\n")
    lines.append(f"**主题**: {title}")
    lines.append(f"**频道**: {channel}")
    lines.append(f"**生成时间**: {now_str}")
    lines.append(f"**分析框架**: {topic}")
    lines.append("")

    # ── 第 0 章: 预测摘要 ──────────────────────────
    lines.append("## 0. 预测摘要\n")
    if debate_result and debate_result.predictions:
        preds = debate_result.predictions[:3]
        lines.append("以下是本次分析提出的 3 个最重要可验证预测：\n")
        for i, p in enumerate(preds, 1):
            lines.append(f"{i}. **{p.prediction}**")
            if p.trigger_condition:
                lines.append(f"   触发条件: {p.trigger_condition}")
            lines.append(f"   提出者: {p.agent}")
            lines.append("")
    else:
        lines.append("*预测摘要基于以下情景分析*\n")

    # ── 第 1 章: 输入与假设 ────────────────────────
    lines.append("---\n")
    lines.append("## 1. 输入与假设\n")
    lines.append(f"**分析主题**: {topic}")
    lines.append(f"**视频标题**: {title}")
    lines.append(f"**数据来源**:")
    lines.append(f"- YouTube 字幕: {len(transcript)} 字符")
    lines.append(f"- 研究简报: {len(research_brief)} 字符 (来自 11 个本地 DB)")
    if social_context:
        lines.append(f"- 社交媒体上下文: {len(social_context)} 字符")
    if sentiment_context:
        lines.append(f"- 市场情绪分析: 已注入")
    if tavily_context:
        lines.append(f"- Tavily 在线搜索: 已注入")
    lines.append("")
    lines.append("**关键假设**:")
    lines.append("- 本地 DB 数据为当前时间点的快照，可能存在时效性延迟")
    lines.append("- YouTube 内容为主观分析，需与 DB 事实交叉验证")
    lines.append("- 预测带有主观概率，不构成投资建议")
    lines.append("")

    # ── 第 2 章: 视频内容分析 ──────────────────────
    lines.append("---\n")
    lines.append("## 2. 视频内容分析\n")
    lines.append("基于转录内容，提取以下核心逻辑链：\n")

    # 从字幕提取关键点
    key_points = _extract_key_points(transcript)
    for point in key_points:
        lines.append(f"- {point}")
    lines.append("")

    # ── 第 3 章: DB 数据验证 ───────────────────────
    lines.append("---\n")
    lines.append("## 3. DB 数据验证（基于11个本地数据库）\n")
    lines.append("针对视频核心观点，以DB事实为准进行交叉验证：\n")
    lines.append(research_brief[:3000])
    lines.append("")

    # ── 第 4 章: 多代理辩论记录 ────────────────────
    lines.append("---\n")
    lines.append("## 4. 多代理辩论记录\n")

    if debate_result:
        # Phase 1: 独立立场
        lines.append("### Phase 1: 独立立场\n")
        for record in debate_result.records:
            lines.append(f"**{record.agent_name}**: {record.stance}")
            lines.append("")

        # Phase 2: 交叉挑战
        if debate_result.cross_challenges:
            lines.append("### Phase 2: 交叉挑战\n")
            for c in debate_result.cross_challenges:
                lines.append(f"**{c['challenger']} 质疑 {c['target']}**:")
                lines.append(c.get("challenge", ""))
                lines.append("")

        # Phase 3: DB 仲裁
        if debate_result.db_arbitrations:
            lines.append("### Phase 3: DB 仲裁\n")
            for a in debate_result.db_arbitrations:
                lines.append(f"**{a['issue']}**:")
                lines.append(a.get("arbitration", ""))
                lines.append("")

        # Phase 4: 共识与分歧
        lines.append("### Phase 4: 共识与分歧\n")
        if debate_result.consensus:
            lines.append("**共识**:")
            for i, c in enumerate(debate_result.consensus, 1):
                lines.append(f"{i}. {c}")
            lines.append("")
        if debate_result.disagreements:
            lines.append("**分歧**:")
            for i, d in enumerate(debate_result.disagreements, 1):
                lines.append(f"{i}. {d.get('point', str(d))}")
            lines.append("")
    else:
        lines.append("*多代理辩论未能完成，以下为基于 DB 数据的综合分析*\n")
        lines.append("### 综合 DB 数据分析\n")
        lines.append(research_brief[:2000])
        lines.append("")

    # ── 第 5 章: 情景预测 ─────────────────────────
    lines.append("---\n")
    lines.append("## 5. 情景预测\n")

    if debate_result and debate_result.predictions:
        lines.append("基于多代理辩论的共识与分歧，以下是最可能的三种情景：\n")
        # 基准情景
        lines.append("### 情景 A: 基准情景 (50%)")
        lines.append(f"- **描述**: 市场维持当前波动区间，核心逻辑延续")
        lines.append(f"- **触发条件**: 无重大外部冲击")
        lines.append(f"- **关键预测**:")
        for p in debate_result.predictions[:2]:
            lines.append(f"  - {p.prediction} (概率: {p.predicted_prob:.0%})")
        lines.append("")
        # 悲观情景
        lines.append("### 情景 B: 悲观情景 (25%)")
        lines.append(f"- **描述**: 外部冲击导致市场下跌")
        lines.append(f"- **触发条件**: 地缘升级 / 流动性危机")
        lines.append(f"- **应对**: 增加现金仓位，启用对冲")
        lines.append("")
        # 乐观情景
        lines.append("### 情景 C: 乐观情景 (25%)")
        lines.append(f"- **描述**: 积极催化推动市场上涨")
        lines.append(f"- **触发条件**: 政策利好 / 业绩超预期")
        lines.append(f"- **应对**: 加仓成长股，减少对冲")
        lines.append("")
    else:
        lines.append("### 情景 A: 基准情景 (50%)")
        lines.append("- 市场维持当前趋势，波动率处于中等水平\n")
        lines.append("### 情景 B: 悲观情景 (25%)")
        lines.append("- 外部冲击导致市场回调，需启动对冲策略\n")
        lines.append("### 情景 C: 乐观情景 (25%)")
        lines.append("- 积极催化推动市场突破关键阻力\n")

    # ── 第 6 章: 预测记分卡 ───────────────────────
    lines.append("---\n")
    lines.append("## 6. 预测记分卡\n")
    try:
        sys_path_backup = list(__import__("sys").path)
        __import__("sys").path.insert(0, str(_MONO_ROOT / "mirofish" / "src"))
        from v4.prediction_store import PredictionStore
        stats = PredictionStore().get_stats()
        lines.append(f"- **总预测数**: {stats['total_predictions']}")
        lines.append(f"- **已验证**: {stats['verified_count']}")
        lines.append(f"- **命中率**: {stats['hit_rate']}")
        lines.append(f"- **Brier Score**: {stats['brier_score']}")
        lines.append(f"- **校准偏差**: {stats['calibration_bias']}")
        lines.append(f"- **整体评级**: {stats['rating']}")
        __import__("sys").path = sys_path_backup
    except Exception as e:
        lines.append(f"*记分卡数据获取失败: {e}*")
    lines.append("")

    # ── 第 7 章: 行动建议 ─────────────────────────
    lines.append("---\n")
    lines.append("## 7. 行动建议\n")

    suggestions = _generate_suggestions(topic, debate_result, research_brief, topic_config=topic_config)
    suggestion_fields = getattr(topic_config, 'suggestion_fields', None) or ["行动", "触发条件", "仓位", "止损", "验证"]
    for i, s in enumerate(suggestions, 1):
        lines.append(f"### 建议 {i}: {s['title']}")
        for field_name in suggestion_fields:
            if field_name in s:
                lines.append(f"- **{field_name}**: {s[field_name]}")
        lines.append("")

    lines.append("> **免责声明**: 本报告基于公开数据与视频内容生成，不构成直接投资建议。")
    lines.append("> 市场具有不确定性，请结合自身风险承受能力独立决策。")
    lines.append("")

    return "\n".join(lines)


def _extract_key_points(transcript: str, max_points: int = 6) -> list:
    """从字幕提取关键逻辑链"""
    # 提取包含关键词的行
    key_sentences = []
    lines = transcript.split('\n')
    for line in lines:
        line = line.strip()
        if len(line) < 20:
            continue
        # 包含关键信号的句子
        signals = [
            '认为', '预计', '趋势', '风险', '机会',
            '因为', '所以', '如果', '可能', '重要',
            '上涨', '下跌', '买入', '卖出', '关注',
        ]
        if any(s in line for s in signals):
            key_sentences.append(line)

    # 取最有信息量的几条
    key_sentences.sort(key=len, reverse=True)
    key_sentences = key_sentences[:max_points]

    # 如果没有提取到足够的点，返回默认值
    if not key_sentences:
        key_sentences = ["基于视频转录内容，提取核心分析逻辑如下"]

    return [s[:200] for s in key_sentences]


def _generate_suggestions(topic, debate_result, research_brief, topic_config=None) -> list:
    """生成行动建议（主题感知）"""
    suggestions = []

    category = None
    if topic_config is not None:
        category = getattr(topic_config, 'category', None)
        # Handle enum as string for comparison
        if category is not None:
            category = str(category).split('.')[-1].lower() if '.' in str(category) else str(category).lower()

    if category in ('financial', 'topiccategory.financial', None):
        suggestions.extend(_generate_financial_suggestions(debate_result, research_brief))
    elif 'war' in str(category) or 'conflict' in str(category):
        suggestions.extend(_generate_war_suggestions(debate_result, research_brief))
    elif 'social' in str(category) or 'lifestyle' in str(category):
        suggestions.extend(_generate_social_suggestions(debate_result, research_brief))
    elif 'travel' in str(category) or 'nomad' in str(category):
        suggestions.extend(_generate_travel_suggestions(debate_result, research_brief))
    elif 'technology' in str(category):
        suggestions.extend(_generate_technology_suggestions(debate_result, research_brief))
    else:
        # 主题关键词兜底
        if "美股" in topic or "宏观" in topic:
            suggestions.extend(_generate_financial_suggestions(debate_result, research_brief))
        elif "加密" in topic:
            suggestions.extend(_generate_crypto_suggestions())
        else:
            suggestions.extend(_generate_financial_suggestions(debate_result, research_brief))

    return suggestions


def _generate_financial_suggestions(debate_result, research_brief) -> list:
    """金融主题建议"""
    suggestions = [
        {"title": "维持防御性仓位",
         "行动": "保持 25-30% 现金作为战术缓冲",
         "触发条件": "VIX 突破 25 或标普 500 跌破关键支撑",
         "仓位": "总仓位 25-30%",
         "止损": "大盘跌破支撑线时增加现金至 40%",
         "验证": "每周检查 VIX 和标普 500 位置",
         "数据支撑": "market_data, 13F"},
        {"title": "逢低布局优质标的",
         "行动": "分批买入被错杀的核心资产",
         "触发条件": "优质公司 PE 回落至历史低位",
         "仓位": "单次建仓不超过总仓位 3%",
         "止损": "基本面恶化（营收增速转负、毛利率下降）",
         "验证": "季度财报验证基本面",
         "数据支撑": "company_fundamentals, SEC"},
    ]
    return suggestions


def _generate_crypto_suggestions() -> list:
    """加密货币主题建议"""
    suggestions = [
        {"title": "控制加密货币仓位",
         "行动": "加密资产占总仓位不超过 10%",
         "触发条件": "BTC 突破关键阻力位",
         "仓位": "总仓位 5-10%",
         "止损": "BTC 跌破 200 日均线",
         "验证": "链上数据验证机构持仓变化"},
    ]
    return suggestions


def _generate_war_suggestions(debate_result, research_brief) -> list:
    """战争/冲突主题建议"""
    return [
        {"title": "关注撤离通道与安全路线",
         "行动": "持续关注外交部及领事馆发布的撤离公告",
         "触发条件": "官方发布撤离指南或人道主义走廊开放",
         "风险评估": "航线/陆路可能因天气或冲突临时中断",
         "备选方案": "准备多条撤离路线（空中、陆路、海上）",
         "信息源": "外交部网站、当地领事馆、国际红十字会"},
        {"title": "应急物资与文档准备",
         "行动": "提前准备应急包（护照复印件、现金、药品、通讯设备）",
         "触发条件": "冲突升级至所在城市或周边区域",
         "风险评估": "基础设施可能中断（电力、网络、银行）",
         "备选方案": "多地点分散存放重要文档和物资",
         "信息源": "旅行安全指南、当地华人社群"},
    ]


def _generate_social_suggestions(debate_result, research_brief) -> list:
    """社会生活主题建议"""
    return [
        {"title": "理解结构性趋势",
         "核心观点": "从社会学和经济学双重视角理解现象背后的结构性力量",
         "趋势判断": "关注长期人口和经济趋势，而非短期个案",
         "关键视角": "媒体叙事可能放大或遮蔽真实的社会变迁",
         "认知框架": "将个体选择置于更大的社会结构中去理解"},
        {"title": "多元信息渠道验证",
         "核心观点": "不同来源的信息可能呈现截然不同的图景",
         "趋势判断": "社交媒体情绪不代表整体民意",
         "关键视角": "历史先例可以提供重要参照",
         "认知框架": "交叉验证多种视角，避免单一叙事陷阱"},
    ]


def _generate_travel_suggestions(debate_result, research_brief) -> list:
    """旅行/生活方式主题建议"""
    return [
        {"title": "目的地安全与可行性评估",
         "行动": "持续关注目的地的安全局势和政策变化",
         "触发条件": "目的地安全评级变化或签证政策调整",
         "风险评估": "地缘冲突、自然灾害、政策突变",
         "预算参考": "预留额外 20-30% 应急资金",
         "备选方案": "准备 1-2 个替代目的地"},
        {"title": "本地融入与资源建立",
         "行动": "提前建立当地社交网络和信息渠道",
         "触发条件": "确定长期停留意向",
         "风险评估": "文化差异可能导致沟通障碍",
         "预算参考": "了解当地生活成本和隐性支出",
         "备选方案": "保持灵活的时间和经济计划"},
    ]


def _generate_technology_suggestions(debate_result, research_brief) -> list:
    """科技主题建议"""
    return [
        {"title": "技术趋势跟踪",
         "行动": "关注核心技术的采用曲线和行业渗透率",
         "触发条件": "关键技术指标突破（用户量、性能、成本）",
         "投资参考": "区分技术可行性和商业可行性",
         "验证": "季度行业报告和财报数据",
         "风险评估": "技术迭代速度快，判断窗口期短"},
        {"title": "竞争格局分析",
         "行动": "跟踪主要玩家的市场份额和战略动向",
         "触发条件": "行业整合或新进入者出现",
         "投资参考": "关注护城河和竞争壁垒的可持续性",
         "验证": "市场竞争数据验证",
         "风险评估": "垄断风险或监管干预"},
    ]


def _sanitize_filename(name: str) -> str:
    """清理文件名中的非法字符"""
    name = name.replace("/", " - ").replace("\\", " - ")
    for char in [':', '*', '?', '"', '<', '>', '|']:
        name = name.replace(char, " ")
    # 截取前 40 字符避免文件名过长（中文字符较宽）
    name = name[:40].strip()
    return name


def _init_tavily_client():
    """初始化 Tavily 客户端

    Returns:
        TavilyClient 实例，或 None（如果 TAVILY_API_KEY 未设置）
    """
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        logger.debug("TAVILY_API_KEY 未设置，Tavily 在线搜索不可用")
        return None

    try:
        from tavily import TavilyClient
        return TavilyClient(api_key=api_key)
    except ImportError:
        logger.debug("tavily-python 库未安装")
        return None
    except Exception as e:
        logger.debug(f"TavilyClient 初始化失败: {e}")
        return None


def _build_tavily_brief_section(tavily_data: dict) -> str:
    """将 Tavily 搜索结果格式化为研究简报章节

    结果标记为 [在线搜索, 需交叉验证] 以区别于本地 DB 数据。

    Args:
        tavily_data: {"results": [{"title": ..., "snippet": ..., "url": ...}, ...]}

    Returns:
        Markdown 格式的 Tavily 数据章节
    """
    lines = ["\n## Tavily 在线搜索结果 [在线搜索, 需交叉验证]"]

    for i, r in enumerate(tavily_data.get("results", [])[:8], 1):
        title = r.get("title", "N/A")
        snippet = (r.get("snippet") or "N/A")[:300]
        url = r.get("url", "N/A")
        source = r.get("source", "N/A")
        lines.append(f"\n### {i}. {title} [{source}]")
        lines.append(snippet)
        if url != "N/A":
            lines.append(f"来源: {url}")

    lines.append("")
    return "\n".join(lines)
