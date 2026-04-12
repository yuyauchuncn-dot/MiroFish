#!/usr/bin/env python3
"""MiroFish v4 多代理辩论引擎

核心理念: 6 个独立代理基于各自认知偏差和 DB 数据偏好进行辩论，
通过 DB 仲裁解决分歧，最终提取共识和保留分歧。

辩论流程:
  Phase 1: 独立立场 — 每个代理发表观点（含 DB 引用 + 可验证预测）
  Phase 2: 交叉挑战 — 代理之间互相质疑
  Phase 3: DB 仲裁 — 用本地 DB 数据裁决分歧
  Phase 4: 共识提取 — 列出一致观点和保留分歧
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from .prediction_store import Prediction, PredictionStore

logger = logging.getLogger(__name__)

# ── 6 个代理定义 ──────────────────────────────────────────────────

@dataclass
class AgentProfile:
    """辩论代理画像"""
    name: str
    name_en: str
    background: str          # 背景原型
    cognitive_bias: str      # 认知偏差
    focus: str              # 关注焦点
    db_preference: str      # DB 数据偏好
    system_prompt: str      # 个性化 system prompt

AGENTS = [
    AgentProfile(
        name="量化分析师",
        name_en="quant",
        background="对冲基金 Quant，10 年统计套利经验",
        cognitive_bias="过度依赖历史数据，低估黑天鹅事件概率",
        focus="资金流向、波动率、统计信号、技术面背离",
        db_preference="market_data, 13F 机构持仓",
        system_prompt=(
            "你是量化分析师，对冲基金 Quant 出身。你的分析基于历史数据和统计信号，"
            "关注资金流向、波动率变化和技术面背离。你倾向于相信数据而非叙事，"
            "对无法量化的论点持怀疑态度。你需要注意：不要过度拟合历史数据，"
            "黑天鹅事件虽然罕见但影响巨大。"
        )
    ),
    AgentProfile(
        name="周期主义者",
        name_en="cyclical",
        background="宏观策略师，擅长历史周期对比",
        cognitive_bias="过度拟合历史周期，忽视结构性变化",
        focus="历史对比、周期位置、领先指标、季节性模式",
        db_preference="news.db 历史新闻 + livenews 实时快讯, research_reports",
        system_prompt=(
            "你是周期主义者，宏观策略师出身。你擅长将当前市场与历史周期进行对比，"
            "关注领先指标和季节性模式。你相信历史会重演。但需要注意："
            "结构性变化可能打破历史模式，不要生搬硬套。"
        )
    ),
    AgentProfile(
        name="基本面投资者",
        name_en="fundamental",
        background="价值投资者，巴菲特/Munger 式分析",
        cognitive_bias="低估市场非理性可以持续的时间",
        focus="财务指标、估值水平、竞争壁垒、管理层质量",
        db_preference="company_fundamentals, SEC filing 原文",
        system_prompt=(
            "你是基本面投资者，信奉价值投资理念。你关注公司的财务指标、估值水平、"
            "竞争壁垒和管理层质量。你相信价格最终会回归价值。但需要注意："
            "市场非理性的时间可能比你想象的更长，'市场保持非理性的时间可以长过你保持 solvent 的时间'。"
        )
    ),
    AgentProfile(
        name="叙事交易者",
        name_en="narrative",
        background="社交媒体驱动的短交易者",
        cognitive_bias="易受叙事驱动，忽视估值和风险",
        focus="市场情绪、叙事可信度、催化剂、资金轮动",
        db_preference="important_persons, news.db + livenews 情绪分析",
        system_prompt=(
            "你是叙事交易者，擅长捕捉市场情绪变化和叙事轮动。你关注社交媒体情绪、"
            "关键人物的言论、以及可能成为催化剂的事件。你行动迅速，但也容易"
            "被叙事迷惑而忽视估值。需要注意：叙事可能很动听，但估值最终会回归。"
        )
    ),
    AgentProfile(
        name="地缘分析师",
        name_en="geopolitical",
        background="国际关系专家，前智库分析师",
        cognitive_bias="过度关注地缘风险，低估市场适应性",
        focus="政策变化、地缘冲突、供应链重组、能源安全",
        db_preference="news.db 地缘新闻 + livenews 实时快讯, evidence_sources",
        system_prompt=(
            "你是地缘分析师，国际关系专家出身。你关注政策变化、地缘冲突、"
            "供应链重组和能源安全。你认为地缘风险是市场最大的不确定性来源。"
            "但需要注意：市场对地缘风险有快速适应的能力，不要过度悲观。"
        )
    ),
    AgentProfile(
        name="风控官",
        name_en="risk",
        background="首席风险官，经历过 2008 金融危机",
        cognitive_bias="过度保守，低估上行空间",
        focus="尾部风险、流动性、杠杆水平、相关性崩溃",
        db_preference="所有 DB，重点寻找矛盾信号",
        system_prompt=(
            "你是风控官，经历过 2008 年金融危机。你的职责是识别尾部风险、"
            "监控流动性和杠杆水平。你倾向于保守，关注最坏情况。"
            "但需要注意：过度保守会错失上行机会，平衡风险与收益。"
        )
    ),
]


@dataclass
class DebateRecord:
    """辩论记录"""
    agent_name: str
    stance: str                      # 独立立场
    db_references: List[str] = field(default_factory=list)  # DB 引用
    verifiable_prediction: str = ""  # 可验证预测
    challenges_received: List[Dict] = field(default_factory=list)
    responses: List[str] = field(default_factory=list)


@dataclass
class DebateResult:
    """完整辩论结果"""
    records: List[DebateRecord]           # 6 个代理的辩论记录
    cross_challenges: List[Dict]          # 交叉挑战 [{challenger, target, challenge, response}]
    db_arbitrations: List[Dict]           # DB 仲裁 [{issue, query_result, conclusion}]
    consensus: List[str]                  # 共识观点
    disagreements: List[Dict]             # 保留分歧 [{point, agents, reason}]
    predictions: List[Prediction]         # 可验证预测
    raw_text: str = ""                    # 原始辩论文本


class DebateEngine:
    """多代理辩论引擎"""

    def __init__(self, prediction_store: PredictionStore = None):
        self.store = prediction_store or PredictionStore()
        self._llm_call: Optional[Callable] = None

    def set_llm_call(self, llm_call: Callable):
        """设置 LLM 调用函数"""
        self._llm_call = llm_call

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """调用 LLM"""
        if self._llm_call is None:
            raise RuntimeError("LLM 调用函数未设置，请先调用 set_llm_call()")
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self._llm_call(messages)

    def run_debate(
        self,
        topic: str,
        research_brief: str,
        llm_call: Callable,
        report_id: str = "",
        query_dispatcher=None,
        agents: Optional[List[AgentProfile]] = None,
        natural_tensions: Optional[List[tuple]] = None,
    ) -> DebateResult:
        """运行完整的多代理辩论流程

        Args:
            topic: 分析主题
            research_brief: 研究简报（来自 compile_brief_v4）
            llm_call: LLM 调用函数
            report_id: 关联报告 ID
            query_dispatcher: QueryDispatcher 实例（可选，支持按需查询）
            agents: 自定义代理列表（可选，默认使用内置 6 个金融代理）
            natural_tensions: 自定义挑战对（可选，默认使用内置张力对）

        Returns:
            DebateResult: 完整辩论结果
        """
        self._llm_call = llm_call
        self._query_dispatcher = query_dispatcher
        self._agents = agents or AGENTS
        self._natural_tensions = natural_tensions or [
            ("量化分析师", "叙事交易者"),
            ("周期主义者", "基本面投资者"),
            ("地缘分析师", "风控官"),
            ("叙事交易者", "基本面投资者"),
        ]
        start_time = time.time()
        logger.info(f"开始多代理辩论: {topic}")

        # Phase 1: 独立立场
        logger.info("Phase 1: 独立立场")
        records, odq_results = self._phase1_independent_stance(topic, research_brief, report_id)

        # 累积按需查询结果，注入到后续阶段
        augmented_brief = research_brief
        if odq_results:
            injection = self._query_dispatcher.build_injection_block(odq_results) if self._query_dispatcher else ""
            if injection:
                augmented_brief = research_brief + "\n" + injection
                logger.info(f"[ODQ] 研究简报扩充: {len(research_brief)} → {len(augmented_brief)} 字符")

        # Phase 2: 交叉挑战
        logger.info("Phase 2: 交叉挑战")
        cross_challenges, odq_phase2 = self._phase2_cross_challenge(records, topic, augmented_brief)
        odq_results.extend(odq_phase2)

        # 再次扩充
        if odq_phase2:
            injection = self._query_dispatcher.build_injection_block(odq_phase2) if self._query_dispatcher else ""
            if injection:
                augmented_brief += "\n" + injection
                logger.info(f"[ODQ] 研究简报再次扩充: +{len(injection)} 字符")

        # Phase 3: DB 仲裁（由 LLM 模拟，基于已提供的 DB 数据）
        logger.info("Phase 3: DB 仲裁")
        db_arbitrations, odq_phase3 = self._phase3_db_arbitration(records, cross_challenges, augmented_brief)
        odq_results.extend(odq_phase3)

        # Phase 4: 共识提取
        logger.info("Phase 4: 共识提取")
        consensus, disagreements = self._phase4_consensus(records, db_arbitrations)

        # 提取所有可验证预测
        predictions = []
        for r in records:
            if r.verifiable_prediction:
                pred = Prediction(
                    prediction=r.verifiable_prediction,
                    trigger_condition="",
                    predicted_prob=0.5,
                    verify_by="",
                    agent=r.agent_name,
                    report_id=report_id,
                )
                predictions.append(pred)

        elapsed = time.time() - start_time
        odq_count = len(odq_results)
        odq_suffix = f"，按需查询 {odq_count} 次" if odq_count else ""
        logger.info(f"辩论完成，耗时 {elapsed:.1f}s，生成 {len(predictions)} 条预测{odq_suffix}")

        return DebateResult(
            records=records,
            cross_challenges=cross_challenges,
            db_arbitrations=db_arbitrations,
            consensus=consensus,
            disagreements=disagreements,
            predictions=predictions,
        )

    def _phase1_independent_stance(
        self, topic: str, research_brief: str, report_id: str
    ) -> tuple:
        """Phase 1: 每个代理独立发表立场

        Returns:
            (records, odq_results): 代理记录和按需查询结果列表
        """
        records = []
        odq_results = []

        # 构建查询能力提示
        query_hint = ""
        if self._query_dispatcher:
            query_hint = self._query_dispatcher.get_available_types()

        for agent in self._agents:
            prompt = f"""
## 分析主题
{topic}

## 研究简报（DB 数据摘要）
{research_brief}

{query_hint}

## 你的角色
- **背景**: {agent.background}
- **认知偏差**: {agent.cognitive_bias}
- **关注焦点**: {agent.focus}
- **DB 数据偏好**: {agent.db_preference}

## 任务
基于你的视角和研究简报，发表你的独立立场。要求:
1. 给出你对当前市场的核心判断（2-3 句话）
2. 引用至少 1 个简报中的 DB 数据作为支撑
3. 如果需要额外数据，使用 `<QUERY>类型: 具体参数</QUERY>` 标签实时查询（如 `<QUERY>company: NVDA</QUERY>`）
4. 提出 1 个具体的、可验证的预测（需要有时间线和触发条件）

格式:
**核心判断**: [你的立场]
**DB 引用**: [引用简报中的数据]
**可验证预测**: [具体事件，含时间线和触发条件]
**理由**: [1-2 句话解释]
"""
            try:
                response = self._call_llm(agent.system_prompt, prompt)

                # 按需查询: 从响应中提取 <QUERY> 标签
                if self._query_dispatcher:
                    odq = self._query_dispatcher.extract_and_execute(response)
                    if odq["queries"]:
                        # 将查询结果附加到响应中
                        injection_lines = ["\n\n## 实时查询结果"]
                        for qtype, qarg, qresult in odq["queries"]:
                            injection_lines.append(f"\n**DB 实时数据 ({qtype}: {qarg})**:")
                            injection_lines.append(qresult)
                        response = odq["clean_text"] + "\n".join(injection_lines)
                        odq_results.extend(odq["queries"])

                # 简单解析 - 提取可验证预测
                prediction = ""
                for marker in ["可验证预测", "可验证预测:", "可验证预测："]:
                    if marker in response:
                        parts = response.split(marker, 1)
                        if len(parts) > 1:
                            # 取下一行，清理 Markdown 格式
                            line = parts[1].split("\n")[0].strip().lstrip(":：").strip()
                            line = line.lstrip("**").rstrip("**").strip()
                            if line and len(line) > 10:
                                prediction = line
                                break

                record = DebateRecord(
                    agent_name=agent.name,
                    stance=response,
                    verifiable_prediction=prediction,
                )
                records.append(record)
                logger.info(f"  {agent.name}: 完成 ({len(response)} 字符)")
            except Exception as e:
                logger.error(f"  {agent.name}: 失败 — {e}")
                records.append(DebateRecord(
                    agent_name=agent.name,
                    stance=f"分析失败: {e}",
                ))

        return records, odq_results

    def _phase2_cross_challenge(
        self, records: List[DebateRecord], topic: str, research_brief: str
    ) -> tuple:
        """Phase 2: 代理之间交叉挑战

        Returns:
            (challenges, odq_results): 挑战记录和按需查询结果
        """
        challenges = []
        odq_results = []
        # 选择 2-3 对最有价值的挑战
        challenge_pairs = self._select_challenge_pairs(records)

        query_hint = ""
        if self._query_dispatcher:
            query_hint = self._query_dispatcher.get_available_types()

        for challenger_name, target_name, target_stance in challenge_pairs:
            challenge_prompt = f"""
## 背景
你正在参与关于 "{topic}" 的多代理辩论。

## 被挑战方的立场
**{target_name} 的观点**:
{target_stance[:500]}

## 研究简报摘要
{research_brief[:2000]}

{query_hint}

## 你的任务
作为 {challenger_name}，从你的视角质疑 {target_name} 的观点。
要求:
1. 指出其论点中的具体漏洞或矛盾
2. 引用 DB 数据支撑你的质疑
3. 如果需要额外数据，使用 `<QUERY>类型: 具体参数</QUERY>` 标签实时查询（如 `<QUERY>credit: TED spread</QUERY>`）
4. 提出一个对方必须回答的具体问题

格式:
**质疑**: [具体质疑内容]
**DB 证据**: [引用数据]
**问题**: [必须回答的问题]
"""
            try:
                challenger_agent = next(a for a in self._agents if a.name == challenger_name)
                response = self._call_llm(challenger_agent.system_prompt, challenge_prompt)

                # 按需查询
                if self._query_dispatcher:
                    odq = self._query_dispatcher.extract_and_execute(response)
                    if odq["queries"]:
                        injection_lines = ["\n\n## 实时查询结果"]
                        for qtype, qarg, qresult in odq["queries"]:
                            injection_lines.append(f"\n**DB 实时数据 ({qtype}: {qarg})**:")
                            injection_lines.append(qresult)
                        response = odq["clean_text"] + "\n".join(injection_lines)
                        odq_results.extend(odq["queries"])

                challenges.append({
                    "challenger": challenger_name,
                    "target": target_name,
                    "challenge": response,
                    "response": "",  # 回应由后续生成
                })
                logger.info(f"  {challenger_name} 质疑 {target_name}: 完成")
            except Exception as e:
                logger.error(f"  交叉挑战失败: {challenger_name} → {target_name} — {e}")

        return challenges, odq_results

    def _phase3_db_arbitration(
        self, records: List[DebateRecord], challenges: List[Dict], research_brief: str
    ) -> tuple:
        """Phase 3: DB 仲裁 — 基于已有 DB 数据裁决分歧

        Returns:
            (arbitrations, odq_results): 仲裁记录和按需查询结果
        """
        arbitrations = []
        odq_results = []

        query_hint = ""
        if self._query_dispatcher:
            query_hint = self._query_dispatcher.get_available_types()

        for challenge in challenges:
            arb_prompt = f"""
## 辩论分歧
- **{challenge['challenger']} 的质疑**: {challenge['challenge'][:300]}

## 现有 DB 数据摘要
{research_brief[:1500]}

{query_hint}

## 仲裁任务
基于上述 DB 数据，判断这场分歧:
1. 数据是否明确支持某一方？
2. 如果需要额外数据，使用 `<QUERY>类型: 具体参数</QUERY>` 标签实时查询（如 `<QUERY>credit: TED spread</QUERY>`）
3. 如果数据不足或矛盾，标记为 "⚠️ 数据不足，保留分歧"
4. 永远不要强行制造共识

格式:
**DB 仲裁**: [查询结果摘要]
**裁决**: 支持 [代理名] / ⚠️ 数据不足
**理由**: [简要解释]
"""
            try:
                # 用风控官的中立视角进行仲裁（优先查找名称包含"风险"或 name_en 含 "risk" 的代理）
                risk_agent = next(
                    (a for a in self._agents if "风险" in a.name or "risk" in a.name_en.lower()),
                    self._agents[0],  # fallback to first agent
                )
                response = self._call_llm(
                    risk_agent.system_prompt + "\n你是中立的仲裁者，用 DB 数据裁决分歧。",
                    arb_prompt
                )

                # 按需查询: 仲裁阶段如果代理发现需要额外数据，可以查询
                if self._query_dispatcher:
                    odq = self._query_dispatcher.extract_and_execute(response)
                    if odq["queries"]:
                        injection_lines = ["\n\n## 实时查询结果"]
                        for qtype, qarg, qresult in odq["queries"]:
                            injection_lines.append(f"\n**DB 实时数据 ({qtype}: {qarg})**:")
                            injection_lines.append(qresult)
                        response = odq["clean_text"] + "\n".join(injection_lines)
                        odq_results.extend(odq["queries"])

                supports = "支持" in response
                if "数据不足" in response or "⚠️" in response:
                    supports = False

                arbitrations.append({
                    "issue": f"{challenge['challenger']} vs {challenge['target']}",
                    "arbitration": response,
                    "supports": challenge['challenger'] if supports else None,
                })
                challenge["response"] = response[:200]  # 简略回应
            except Exception as e:
                logger.error(f"  DB 仲裁失败: {e}")

        return arbitrations, odq_results

    def _phase4_consensus(
        self, records: List[DebateRecord], arbitrations: List[Dict]
    ) -> tuple:
        """Phase 4: 共识提取 — 列出一致观点和保留分歧"""
        # 简单提取：找出多个代理都提到的观点
        all_stances = "\n\n".join(f"**{r.agent_name}**: {r.stance[:200]}" for r in records)

        consensus_prompt = f"""
## 6 个代理的独立立场

{all_stances}

## DB 仲裁结果

{json.dumps([{'issue': a['issue'], 'result': a['arbitration'][:200]} for a in arbitrations], ensure_ascii=False)}

## 共识提取任务
1. 列出所有代理达成一致的观点（至少 4/6 代理隐含同意）
2. 列出仍存在分歧的观点，说明哪几个代理有分歧

格式:
**共识**:
1. [观点 1] — X/6 代理同意
2. [观点 2] — X/6 代理同意

**分歧**:
1. [观点 A] — [代理名] vs [代理名]（原因）
2. [观点 B] — [代理名] vs [代理名]（原因）
"""
        try:
            response = self._call_llm(
                "你是辩论主持人，负责提取共识和保留分歧。保持中立。",
                consensus_prompt
            )

            # 解析共识和分歧
            consensus = []
            disagreements = []

            in_consensus = False
            in_disagreement = False
            for line in response.split("\n"):
                line = line.strip()
                if line.startswith("**共识**") or line.startswith("**共识:**"):
                    in_consensus = True
                    in_disagreement = False
                    continue
                elif line.startswith("**分歧**") or line.startswith("**分歧:**"):
                    in_consensus = False
                    in_disagreement = True
                    continue
                elif line.startswith("**") and not line.startswith("***"):
                    in_consensus = False
                    in_disagreement = False
                    continue

                if in_consensus and line and (line[0].isdigit() or line.startswith("-")):
                    consensus.append(line.lstrip("-").strip())
                elif in_disagreement and line and (line[0].isdigit() or line.startswith("-")):
                    disagreements.append({
                        "point": line.lstrip("-").strip(),
                        "agents": "",
                        "reason": "",
                    })

            return consensus, disagreements
        except Exception as e:
            logger.error(f"  共识提取失败: {e}")
            return [], []

    def _select_challenge_pairs(self, records: List[DebateRecord]) -> List[tuple]:
        """选择最有价值的挑战对"""
        available = {r.agent_name for r in records}
        selected = []
        for challenger, target in self._natural_tensions:
            if challenger in available and target in available:
                target_record = next(r for r in records if r.agent_name == target)
                selected.append((challenger, target, target_record.stance))
                if len(selected) >= 3:
                    break

        return selected

    def format_debate_report(self, result: DebateResult, topic: str) -> str:
        """将辩论结果格式化为 Markdown 报告"""
        lines = [
            f"# MiroFish v4.0 — 多代理辩论记录",
            f"\n**主题**: {topic}",
            f"**生成时间**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}",
            f"**参与代理**: {', '.join(r.agent_name for r in result.records)}",
            "",
            "---",
            "",
            "## Phase 1: 独立立场",
            "",
        ]

        for r in result.records:
            lines.append(f"### {r.agent_name}")
            lines.append(r.stance)
            lines.append("")

        lines.extend(["---", "", "## Phase 2: 交叉挑战", ""])
        for c in result.cross_challenges:
            lines.append(f"### {c['challenger']} 质疑 {c['target']}")
            lines.append(c.get("challenge", ""))
            if c.get("response"):
                lines.append(f"\n### DB 仲裁回应")
                lines.append(c["response"])
            lines.append("")

        lines.extend(["---", "", "## Phase 3: DB 仲裁", ""])
        for a in result.db_arbitrations:
            lines.append(f"### {a['issue']}")
            lines.append(a["arbitration"])
            lines.append("")

        lines.extend(["---", "", "## Phase 4: 共识与分歧", ""])
        if result.consensus:
            lines.append("### 共识")
            for i, c in enumerate(result.consensus, 1):
                lines.append(f"{i}. {c}")
            lines.append("")

        if result.disagreements:
            lines.append("### 分歧")
            for i, d in enumerate(result.disagreements, 1):
                lines.append(f"{i}. {d['point']}")
            lines.append("")

        return "\n".join(lines)
