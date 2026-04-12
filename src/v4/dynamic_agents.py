#!/usr/bin/env python3
"""MiroFish v4 动态代理生成

根据视频内容提取关键实体，模板化组合视频特定的分析代理。
动态代理 AUGMENT 静态分类代理（不替代），总代理数上限 8。

使用方式：
    from analysis.mirofish.dynamic_agents import (
        extract_entities, compose_dynamic_agents, compose_debate_team
    )
    entities = extract_entities(transcript, title)
    dynamic = compose_dynamic_agents(entities, primary_category, max_agents=2)
    final_agents, final_tensions = compose_debate_team(
        static_agents=topic_config.agents,
        dynamic_agents=dynamic,
        static_tensions=topic_config.natural_tensions,
        max_total_agents=8,
    )
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .topic_config import AgentProfile, TopicCategory


@dataclass
class EntityContext:
    """从文本中提取的实体及其上下文"""
    name: str
    entity_type: str  # company, technology, person, event, location, asset
    context_snippet: str
    domain_hint: str  # 从上下文推断的领域


# ── 实体提取规则 ───────────────────────────────────────────────────

# 公司名称映射（常见中英文）
_COMPANY_PATTERNS = {
    r'nvda|nvidia': ('NVDA', 'company'),
    r'tesla|tsla|特斯拉': ('TSLA', 'company'),
    r'amd': ('AMD', 'company'),
    r'apple|aapl|苹果': ('AAPL', 'company'),
    r'microsoft|msft|微软': ('MSFT', 'company'),
    r'google|googl|alphabet|谷歌': ('GOOGL', 'company'),
    r'amazon|amzn|亚马逊': ('AMZN', 'company'),
    r'meta|facebook|fb': ('META', 'company'),
    r'anthropic': ('Anthropic', 'company'),
    r'openai': ('OpenAI', 'company'),
    r'华为': ('华为', 'company'),
    r'腾讯|wechat': ('腾讯', 'company'),
    r'阿里|alibaba': ('阿里', 'company'),
    r'百度|baidu': ('百度', 'company'),
    r'字节跳动|byt e': ('字节跳动', 'company'),
    r'台积电|tsmc': ('台积电', 'company'),
    r'asml': ('ASML', 'company'),
    r'oracle|甲骨文': ('Oracle', 'company'),
    r'nokia|诺基亚': ('Nokia', 'company'),
    r'intel|英特尔': ('Intel', 'company'),
    r'三星|samsung': ('三星', 'company'),
    r'高通|qualcomm': ('Qualcomm', 'company'),
    r'palantir|pltr': ('PLTR', 'company'),
}

# 资产/商品名称
_ASSET_PATTERNS = {
    r'黄金|gold': ('黄金', 'asset'),
    r'白银|silver': ('白银', 'asset'),
    r'原油|oil|石油': ('原油', 'asset'),
    r'铜|copper': ('铜', 'asset'),
    r'比特币|bitcoin|btc': ('比特币', 'asset'),
    r'以太坊|ethereum|eth': ('以太坊', 'asset'),
}

# 人物名称（带标题前缀的上下文）
_PERSON_PATTERNS = [
    r'(马斯克|musk)',
    r'(鲍威尔|powell)',
    r'(黄仁勋|jensen)',
    r'(扎克伯格|zuckerberg)',
    r'(库克|tim cook)',
    r'(纳德拉|nadella)',
    r'(孙宇晨|justin sun)',
    r'(赵长鹏|cchangpeng|cz)',
    r'(刘晓春)',
    r'(张丹丹)',
]

# 事件关键词
_EVENT_KEYWORDS = [
    '财报', '加息', '降息', '制裁', '选举', '裁员', '并购', '上市',
    'ipo', 'earnings', 'fed meeting', 'rate hike', 'rate cut',
    '关税', '贸易战', '脱钩', '禁令', '出口管制',
]

# 技术关键词
_TECH_KEYWORDS = [
    'ai', '人工智能', '大模型', 'llm', 'gpt', '芯片', '半导体',
    '自动驾驶', '量子', '区块链', 'nft', ' defi', 'web3',
    'agent', '智能体', 'transformer', 'attention',
]


def extract_entities(transcript: str, title: str, top_n: int = 5) -> List[EntityContext]:
    """从字幕和标题中提取关键实体。

    使用正则 + 频率统计提取公司、资产、人物、事件、技术等实体。
    返回按上下文频率排序的 top N 实体。

    Args:
        transcript: 字幕/文章内容
        title: 标题
        top_n: 返回的实体数量

    Returns:
        排序后的实体列表
    """
    text = title + "\n" + transcript
    text_lower = text.lower()
    found: Dict[str, EntityContext] = {}

    # 1. 公司名称提取
    for pattern, (name, etype) in _COMPANY_PATTERNS.items():
        match = re.search(pattern, text_lower)
        if match:
            count = len(re.findall(pattern, text_lower))
            start = max(0, match.start() - 20)
            end = min(len(text), match.end() + 20)
            snippet = text[start:end].strip()
            if name not in found:
                found[name] = EntityContext(name, etype, snippet, 'technology')

    # 2. 资产/商品提取
    for pattern, (name, etype) in _ASSET_PATTERNS.items():
        match = re.search(pattern, text_lower)
        if match:
            count = len(re.findall(pattern, text_lower))
            start = max(0, match.start() - 20)
            end = min(len(text), match.end() + 20)
            snippet = text[start:end].strip()
            if name not in found:
                domain = 'finance' if name in ('比特币', '以太坊') else 'commodities'
                found[name] = EntityContext(name, etype, snippet, domain)

    # 3. 人物名称提取
    for pattern in _PERSON_PATTERNS:
        match = re.search(pattern, text)
        if match:
            name = match.group(1)
            start = max(0, match.start() - 20)
            end = min(len(text), match.end() + 20)
            snippet = text[start:end].strip()
            if name not in found:
                found[name] = EntityContext(name, 'person', snippet, 'general')

    # 4. 事件关键词提取（带频率）
    for kw in _EVENT_KEYWORDS:
        matches = list(re.finditer(re.escape(kw.lower()), text_lower))
        if matches:
            count = len(matches)
            snippet = text[matches[0].start():matches[0].end() + 30].strip()
            if kw not in found:
                found[kw] = EntityContext(kw, 'event', snippet, 'finance')

    # 5. 技术关键词提取（带频率）
    for kw in _TECH_KEYWORDS:
        matches = list(re.finditer(re.escape(kw.lower()), text_lower))
        if matches:
            count = len(matches)
            snippet = text[matches[0].start():matches[0].end() + 30].strip()
            if kw not in found:
                found[kw] = EntityContext(kw, 'technology', snippet, 'technology')

    # 按频率排序（简单启发式：在文本中出现次数）
    def _count_entity(e: EntityContext) -> int:
        return text_lower.count(e.name.lower())

    sorted_entities = sorted(found.values(), key=_count_entity, reverse=True)
    return sorted_entities[:top_n]


# ── 代理模板 ──────────────────────────────────────────────────────
# 键：(实体类型, 主题分类) → 代理模板
_AGENT_TEMPLATES: Dict[Tuple[str, TopicCategory], Dict[str, str]] = {
    ("company", TopicCategory.FINANCIAL): {
        "name_format": "{entity} 分析师",
        "name_en_format": "{entity_lower}_analyst",
        "background": "{entity} 专注研究员，覆盖该股票 5+ 年",
        "cognitive_bias": "个股深度了解可能导致过度集中观点，忽视宏观风险",
        "focus": "{entity} 财报、竞争壁垒、行业地位、估值水平",
        "db_preference": "company_fundamentals, SEC filing, market_data, 13F 持仓",
        "system_prompt": (
            "你是 {entity} 的专注研究员，长期覆盖该股票。你深入了解 {entity} 的业务模式、"
            "财务状况、竞争壁垒和行业地位。你基于对公司基本面的深度理解给出分析。"
            "但需要注意：对单一公司的深度了解可能导致你忽视行业整体趋势和宏观风险。"
        ),
    },
    ("company", TopicCategory.TECHNOLOGY): {
        "name_format": "{entity} 产品分析师",
        "name_en_format": "{entity_lower}_product",
        "background": "{entity} 产品线深度研究者",
        "cognitive_bias": "产品思维，可能忽视商业变现挑战",
        "focus": "{entity} 技术路线、产品竞争力、用户体验、生态位",
        "db_preference": "tavily 在线搜索, news.db 科技报道",
        "system_prompt": (
            "你是 {entity} 产品线的深度研究者。你关注 {entity} 的技术路线、"
            "产品竞争力、用户体验和市场生态位。"
            "但需要注意：好的技术产品不等于好的商业回报。"
        ),
    },
    ("company", TopicCategory.MACRO_STRATEGY): {
        "name_format": "{entity} 策略师",
        "name_en_format": "{entity_lower}_strategist",
        "background": "{entity} 宏观影响分析师",
        "cognitive_bias": "公司中心视角，可能忽视行业联动",
        "focus": "{entity} 对宏观经济的影响、政策关联、系统性重要程度",
        "db_preference": "news.db 宏观报道, macro_economic",
        "system_prompt": (
            "你是 {entity} 的宏观影响分析师。你关注 {entity} 对宏观经济的影响、"
            "政策关联和系统性重要程度。"
            "但需要注意：单个公司不能完全代表宏观趋势。"
        ),
    },
    ("asset", TopicCategory.COMMODITIES): {
        "name_format": "{entity} 分析师",
        "name_en_format": "{entity_lower}_analyst",
        "background": "{entity} 市场研究员，产业链覆盖经验",
        "cognitive_bias": "单一品种聚焦，可能忽视跨品种联动",
        "focus": "{entity} 供需格局、价格驱动、库存周期、替代品竞争",
        "db_preference": "news.db 大宗商品报道, market_data, tavily 在线搜索",
        "system_prompt": (
            "你是 {entity} 市场研究员，覆盖该品种产业链。你关注 {entity} 的供需格局、"
            "价格驱动因素、库存周期和替代品竞争。"
            "但需要注意：单一品种的价格受跨品种和宏观因素的强烈影响。"
        ),
    },
    ("asset", TopicCategory.FINANCIAL): {
        "name_format": "{entity} 策略师",
        "name_en_format": "{entity_lower}_strategist",
        "background": "{entity} 投资分析师",
        "cognitive_bias": "品种偏好，可能忽视资产配置全局",
        "focus": "{entity} 投资逻辑、风险收益特征、相关性、配置价值",
        "db_preference": "market_data, news.db",
        "system_prompt": (
            "你是 {entity} 投资分析师。你关注 {entity} 的投资逻辑、"
            "风险收益特征、与其他资产的相关性和配置价值。"
            "但需要注意：单个资产的表现不能脱离整体投资组合。"
        ),
    },
    ("technology", TopicCategory.TECHNOLOGY): {
        "name_format": "{entity} 技术专家",
        "name_en_format": "{entity_lower}_expert",
        "background": "{entity} 领域技术专家",
        "cognitive_bias": "技术乐观主义，可能低估落地难度",
        "focus": "{entity} 技术成熟度、应用前景、竞争替代、瓶颈突破",
        "db_preference": "tavily 在线搜索, news.db 科技报道, research_reports",
        "system_prompt": (
            "你是 {entity} 领域的技术专家。你关注 {entity} 的技术成熟度、"
            "应用前景、竞争替代和瓶颈突破。"
            "但需要注意：实验室中的技术突破不等于产业化的成功。"
        ),
    },
    ("person", TopicCategory.FINANCIAL): {
        "name_format": "{entity} 追踪分析师",
        "name_en_format": "{entity_lower}_tracker",
        "background": "关注 {entity} 言论和行为的市场影响",
        "cognitive_bias": "人物中心偏见，可能过度解读个别言论",
        "focus": "{entity} 的公开言论、决策影响、市场预期管理",
        "db_preference": "important_persons, news.db, tavily 在线搜索",
        "system_prompt": (
            "你关注 {entity} 的言论和行为对市场的影响。"
            "你跟踪其公开表态、决策和市场预期之间的差异。"
            "但需要注意：重要人物的言论有时是为了引导预期，而非反映真实意图。"
        ),
    },
    ("event", TopicCategory.FINANCIAL): {
        "name_format": "{entity} 事件分析师",
        "name_en_format": "{entity_lower}_event",
        "background": "事件驱动交易分析师",
        "cognitive_bias": "事件驱动思维，可能忽视长期趋势",
        "focus": "{entity} 事件的市场影响、预期差、波动率冲击、历史模式",
        "db_preference": "news.db, market_data",
        "system_prompt": (
            "你是事件驱动交易分析师，专注 {entity} 事件的市场影响。"
            "你关注预期差、波动率冲击和历史模式。"
            "但需要注意：事件驱动交易的窗口通常很短，长期趋势更重要。"
        ),
    },
    ("event", TopicCategory.MACRO_STRATEGY): {
        "name_format": "{entity} 政策分析师",
        "name_en_format": "{entity_lower}_policy",
        "background": "宏观事件和政策研究者",
        "cognitive_bias": "事件中心偏见，可能忽视结构性力量",
        "focus": "{entity} 事件的宏观影响、政策传导、连锁反应",
        "db_preference": "macro_economic, news.db",
        "system_prompt": (
            "你是宏观事件研究者，关注 {entity} 事件的宏观影响、"
            "政策传导和连锁反应。"
            "但需要注意：单一事件的影响通常被结构性力量所吸收。"
        ),
    },
    ("event", TopicCategory.SOCIAL_OBSERVATION): {
        "name_format": "{entity} 社会影响分析师",
        "name_en_format": "{entity_lower}_social",
        "background": "社会事件影响研究者",
        "cognitive_bias": "事件驱动偏见，可能忽视长期社会趋势",
        "focus": "{entity} 事件的社会影响、群体反应、政策回应",
        "db_preference": "news.db 社会报道, tavily 在线搜索",
        "system_prompt": (
            "你是社会事件影响研究者，关注 {entity} 事件的社会影响、"
            "群体反应和政策回应。"
            "但需要注意：事件的即时反应不等于长期社会趋势。"
        ),
    },
}

# 如果找不到精确匹配，用这个 fallback 模板
_FALLBACK_TEMPLATE = {
    "name_format": "{entity} 分析专家",
    "name_en_format": "{entity_lower}_expert",
    "background": "{entity} 领域研究专家",
    "cognitive_bias": "领域聚焦，可能忽视跨领域联动",
    "focus": "{entity} 相关动态、行业影响、未来趋势",
    "db_preference": "news.db, tavily 在线搜索",
    "system_prompt": (
        "你是 {entity} 领域的研究专家。你关注 {entity} 相关动态、"
        "行业影响和未来趋势。"
        "但需要注意：单一领域的分析需要结合更广泛的宏观和社会背景。"
    ),
}


def _format_template(template: Dict[str, str], entity: EntityContext) -> Dict[str, str]:
    """用实体信息填充模板"""
    entity_lower = entity.name.lower().replace(" ", "_").replace("-", "_")
    ctx = {
        "entity": entity.name,
        "entity_lower": entity_lower,
    }
    return {k: v.format(**ctx) for k, v in template.items()}


def compose_dynamic_agents(
    entities: List[EntityContext],
    primary_category: TopicCategory,
    max_agents: int = 2,
) -> List[AgentProfile]:
    """根据提取的实体组合动态代理。

    模板化组合：根据实体类型（company/asset/technology/person/event）
    和主题分类选择对应的代理模板，填充后生成 AgentProfile。

    Args:
        entities: 提取的实体列表
        primary_category: 主分类
        max_agents: 最多生成的动态代理数

    Returns:
        动态代理列表
    """
    if not entities:
        return []

    agents = []
    for entity in entities[:max_agents * 2]:  # 多找一些，后面去重
        # 选择模板：优先 (entity_type, category)，其次找同 entity_type 的模板，最后 fallback
        key = (entity.entity_type, primary_category)
        if key in _AGENT_TEMPLATES:
            template = _AGENT_TEMPLATES[key]
        else:
            # 尝试找同 entity_type 的模板
            matched = False
            for (etype, _cat), tmpl in _AGENT_TEMPLATES.items():
                if etype == entity.entity_type:
                    template = tmpl
                    matched = True
                    break
            if not matched:
                template = _FALLBACK_TEMPLATE

        filled = _format_template(template, entity)
        agent = AgentProfile(
            name=filled["name_format"],
            name_en=filled["name_en_format"],
            background=filled["background"],
            cognitive_bias=filled["cognitive_bias"],
            focus=filled["focus"],
            db_preference=filled["db_preference"],
            system_prompt=filled["system_prompt"],
        )
        agents.append(agent)

    return agents[:max_agents]


def compose_debate_team(
    static_agents: List[AgentProfile],
    dynamic_agents: List[AgentProfile],
    static_tensions: List[tuple],
    max_total_agents: int = 8,
) -> Tuple[List[AgentProfile], List[tuple]]:
    """组合静态和动态代理，生成最终辩论团队。

    策略：
    1. 保留所有静态代理（经过测试的基准团队）
    2. 去重：按 name_en 去重动态代理
    3. 认知多样性检查：若动态代理与静态代理 bias 关键词重叠 > 50%，
       跳过该动态代理
    4. 张力对：保留 top 2 静态张力 + 动态 vs 静态配对

    Args:
        static_agents: 分类级别的静态代理
        dynamic_agents: 视频级别的动态代理
        static_tensions: 静态张力对
        max_total_agents: 最大代理总数

    Returns:
        (最终代理列表, 最终张力对列表)
    """
    # 1. 从静态代理开始
    final_agents = list(static_agents)
    static_names_en = {a.name_en for a in static_agents}
    static_bias_keywords = set()
    for a in static_agents:
        static_bias_keywords.update(_extract_bias_keywords(a.cognitive_bias))

    # 2. 添加动态代理（去重 + 多样性检查）
    added = 0
    for dyn in dynamic_agents:
        if len(final_agents) >= max_total_agents:
            break
        # name_en 去重
        if dyn.name_en in static_names_en:
            continue
        # 认知多样性检查
        dyn_bias = _extract_bias_keywords(dyn.cognitive_bias)
        overlap = len(dyn_bias & static_bias_keywords)
        if overlap > len(dyn_bias) * 0.5 and len(dyn_bias) > 1:
            # 认知偏差高度重叠，跳过
            continue

        final_agents.append(dyn)
        static_names_en.add(dyn.name_en)
        static_bias_keywords.update(dyn_bias)
        added += 1

    # 3. 构建张力对
    final_tensions = list(static_tensions[:2])  # 保留 top 2 静态张力

    # 添加动态 vs 静态配对
    if added > 0:
        dyn_agent_names = {a.name for a in final_agents[-added:]}
        # 为每个动态代理找一个最相关的静态代理配对
        for dyn in final_agents[-added:]:
            # 找与动态代理 focus 最互补的静态代理
            best_match = _find_complementary(static_agents, dyn)
            if best_match:
                tension = (dyn.name, best_match.name)
                if tension not in final_tensions:
                    final_tensions.append(tension)

    return final_agents, final_tensions


def _extract_bias_keywords(bias: str) -> set:
    """从认知偏差描述中提取关键词"""
    # 简单分词：按标点、空格分割
    import re
    words = re.split(r'[，、,;；\s]+', bias)
    return {w.strip() for w in words if len(w.strip()) >= 2}


def _find_complementary(
    static_agents: List[AgentProfile],
    dynamic: AgentProfile,
) -> Optional[AgentProfile]:
    """找一个与动态代理最有挑战性的静态代理配对"""
    # 简单策略：找 focus 差异最大的静态代理
    dynamic_focus = set(_extract_bias_keywords(dynamic.focus))
    best_match = None
    max_diff = 0

    for sa in static_agents:
        sa_focus = set(_extract_bias_keywords(sa.focus))
        # 差异度：对称差
        diff = len(dynamic_focus ^ sa_focus)
        if diff > max_diff:
            max_diff = diff
            best_match = sa

    return best_match
