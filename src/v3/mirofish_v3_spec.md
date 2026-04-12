# MiroFish v3.0 Report Specification & KPI Framework

**版本：** v3.0  
**更新日期：** 2026-03-21  
**质量标杆：** `analysis/MiroFish_Crypto_Enhanced_20260321.md`  
**框架文档：** `mirofish_dynamic_roles_plan.md`

---

## 1. 报告结构要求

### 标题格式
`MiroFish_[Topic]_Enhanced_[YYYYMMDD].md`

### 必需章节
| 章节 | 字数要求 | 说明 |
|------|----------|------|
| Executive Summary | 1000-1500 字 | 核心发现 + 主要结论 |
| Entity Extraction Table | 完整表格 | 6 类实体（资产/机构/人物/产品/技术/政策） |
| 6 Dynamic Role Analysis | 每个≥500 字 | 每个角色 3+ KPI |
| Risk Assessment Matrix | 4x4 网格 | 概率×影响程度 |
| Final Decision | 3+ 建议 | 可执行投资建议 |
| Personal Positioning | 1 段落 | 个人立场说明 |
| KPI Verification Log | 完整表格 | 所有 KPI 验证状态 |

---

## 2. 动态角色分析要求（6 个固定角色）

### Role 1: Financial Analyst（财务分析师）
**Perspective:** 评估市场资本结构与流动性

**Required KPIs (≥3):**
- 市值/市场规模
- 资金流入/流出数据
- 波动率/风险指标

**示例模板:**
```markdown
## Financial Analyst - 市场资本流动

**Key Metrics**:
- [指标 1]: [数值] ([占比/变化])
- [指标 2]: [数值] ([时间周期])
- [指标 3]: [数值] (vs [基准])

**Validation**:
- Source: [数据源名称] ([日期])
- Data Points: [数据点数量]
- Trend Analysis: [趋势描述]
```

---

### Role 2: Strategy Evaluator（战略评估师）
**Perspective:** 评估历史周期规律与有效性

**Required KPIs (≥3):**
- 历史周期对比（≥2 个时期）
- 有效性窗口分析
- 趋势变化倍数

**示例模板:**
```markdown
## Strategy Evaluator - 周期有效性

**Historical Comparison**:
| 周期 | 日期 | 起始值 | 当前值 | 峰值 | 倍数 |
|------|------|--------|--------|------|------|
| [周期 1] | [日期] | [值] | [值] | [值] | [x] |
| [周期 2] | [日期] | [值] | [值] | [值] | [x] |
| [周期 3] | [日期] | [值] | [值] | [值] | [x] |

**Verdict**: [周期规律是否适用 + 原因]
```

---

### Role 3: Management Analyst（管理分析师）
**Perspective:** 分析运营策略与管理决策

**Required KPIs (≥3):**
- 运营指标（≥2 个量化）
- 团队/结构分析
- 战略转变评估

**示例模板:**
```markdown
## Management Analyst - 运营策略

**Operational Metrics**:
- [指标 1]: [数值] ([变化])
- [指标 2]: [数值] ([对比])

**Strategy Changes**:
| 主体 | 策略转变 | 市场地位 |
|------|----------|----------|
| [主体 1] | [策略] | [地位] |
| [主体 2] | [策略] | [地位] |

**Verdict**: [管理决策评估]
```

---

### Role 4: Competitive Position Analyst（竞争地位分析师）
**Perspective:** 分析竞争格局与护城河

**Required KPIs (≥3):**
- 市场份额对比（≥3 个竞争对手）
- SWOT 分析
- 护城河评估

**示例模板:**
```markdown
## Competitive Position Analyst - 竞争格局

**Competitive Comparison**:
| 竞争对手 | 威胁等级 | 优势 | 劣势 |
|----------|----------|------|------|
| [对手 1] | [等级] | [优势] | [劣势] |
| [对手 2] | [等级] | [优势] | [劣势] |
| [对手 3] | [等级] | [优势] | [劣势] |

**Moat Analysis**:
- ✅ [优势 1]
- ✅ [优势 2]
- ❌ [劣势 1]
- ❌ [劣势 2]

**Verdict**: [竞争地位评估]
```

---

### Role 5: Culture Analyst（文化分析师）
**Perspective:** 评估市场情绪与叙事可信度

**Required KPIs (≥3):**
- 叙事可信度评分
- 市场情绪指标
- 信任/健康度评分

**示例模板:**
```markdown
## Culture Analyst - 市场情绪与叙事

**Narrative Credibility**:
- [叙事 1]: [可信度评估]
- [叙事 2]: [可信度评估]

**Sentiment Indicators**:
1. [指标 1]: [描述]
2. [指标 2]: [描述]
3. [指标 3]: [描述]

**Organizational Health Score**: [X]/10
- [正面因素]
- [负面因素]

**Verdict**: [情绪评估]
```

---

### Role 6: Power Analyst（权力分析师）
**Perspective:** 映射资本流动与决策影响力

**Required KPIs (≥3):**
- 影响力分布（≥5 个参与者）
- 资本流向图
- Power Score 评分

**示例模板:**
```markdown
## Power Analyst - 资本流动与影响力

**Influence Distribution**:
| 参与者 | 影响力 | 关注焦点 | Power Score |
|--------|--------|----------|-------------|
| [参与者 1] | [等级] | [焦点] | [XX]/100 |
| [参与者 2] | [等级] | [焦点] | [XX]/100 |
| [参与者 3] | [等级] | [焦点] | [XX]/100 |

**Capital Flow**:
```
[流向图描述]
```

**Key Dynamics**:
- [动态 1]
- [动态 2]

**Verdict**: [权力格局评估]
```

---

## 3. 数据源引用格式

### 必需数据源（≥3 个）
| 类型 | 示例 | 引用格式 |
|------|------|----------|
| YouTube Transcript | `~/gemini/youtube_downloads/transcripts/` | `Source: [文件名] ([日期])` |
| 新闻 API | 在线搜索 | `Source: [媒体名] ([日期])` |
| 财报/研报 | 公司官网/SEC | `Source: [报告名] ([日期])` |
| 市场数据 | CoinGecko/Bloomberg | `Source: [平台名] ([日期])` |

### 引用示例
```markdown
**Validation**:
- Source: 瑞银研报解读 20250821 (YouTube transcript)
- Source: UBS Q1 2026 Investor Report (官方财报)
- Source: Swiss Banking Association Q1 2026 (行业协会)
- Data Points: 3 个月数据
- Trend Analysis: [趋势描述]
```

---

## 4. 验证 Checklist

### 生成前检查（Pre-generation）
- [ ] 确认 topic 类型（FINANCE/TECH/LIFESTYLE/GEOPOLITICS/REAL_ESTATE/COMPANY）
- [ ] 收集≥3 个数据源
- [ ] 确认 YouTube transcript 路径存在
- [ ] 读取 `mirofish_dynamic_roles_plan.md` 框架

### 生成后检查（Post-generation）
- [ ] 所有 6 个角色存在
- [ ] 每个角色≥500 字
- [ ] 每个角色≥3 个 KPI
- [ ] Entity Extraction 表格完整
- [ ] Risk Matrix 4x4 完整
- [ ] Final Decision 有 3+ 建议
- [ ] Personal Positioning 完成
- [ ] KPI Verification Log 完整
- [ ] 无重复内容（关键检查！）
- [ ] Git commit 包含 batch 号

---

## 5. 批量处理工作流

### 优先级顺序
1. **Batch 1**: Crypto（6 个，已完成）
2. **Batch 2**: 外资投行（UBS/Barclays/Morgan Stanley/Citi/Nomura）~50 个
3. **Batch 3**: 科技/产业（NVDA/AAPL/AMD/META）~40 个
4. **Batch 4**: 宏观/中国经济 ~80 个
5. **Batch 5**: 其他主题 ~193 个

### 每个 Batch 流程
```bash
# 1. 验证
python mirofish_validator.py --batch N

# 2. 生成（spawn subagent）
openclaw spawn --task "Generate MiroFish Batch N reports" --model ollama/qwen3.5:cloud

# 3. 提交
cd ~/gemini/analysis
git add --all
git commit -m "[Batch N] MiroFish reports regenerated to v3.0 standard"

# 4. 归档旧报告
mkdir -p ~/gemini/analysis/deprecated
mv ~/gemini/analysis/MiroFish_*_202603[12][0-9].md ~/gemini/analysis/deprecated/ 2>/dev/null
```

---

## 6. 质量标杆参考

### Crypto_Enhanced_20260321 标准
- Executive Summary: 8 个核心发现
- 6 个角色每个都有 3+ KPI
- 历史周期对比表格完整
- 影响力矩阵 Power Score 精确
- 无重复内容

### UBS 报告试跑验证
- 使用 18 个瑞银 transcript 作为数据源
- 生成后对比旧报告（修复重复 bug）
- 验证 6 个角色深度达标

---

## 7. 可重现步骤（其他 Agent 执行）

### Step 1: 读取框架文档
```bash
read ~/gemini/mirofish_dynamic_roles_plan.md
read ~/gemini/MiroFish/MiroFish_v3.0_Specification.md
```

### Step 2: 收集数据源
```bash
ls ~/gemini/youtube_downloads/transcripts/ | grep -i "[topic]"
cat ~/gemini/youtube_downloads/transcripts/[file].txt
```

### Step 3: 生成报告
```
按 spec 文件 6 个角色模板逐一生成
每个角色≥500 字，3+ KPI
引用≥3 个数据源
```

### Step 4: 验证
```bash
# 检查字数
wc -w MiroFish_[Topic]_Enhanced_20260321.md

# 检查角色数量
grep -c "## Role" MiroFish_[Topic]_Enhanced_20260321.md

# 检查重复
sort MiroFish_[Topic]_Enhanced_20260321.md | uniq -d
```

### Step 5: 提交
```bash
cd ~/gemini/analysis
git add MiroFish_[Topic]_Enhanced_20260321.md
git commit -m "Regenerate [Topic] to v3.0 standard"
```

---

## 8. 常见问题修复

### 重复内容 Bug
**症状:** 同一内容循环多次  
**原因:** subagent 输出重复  
**修复:** 生成后运行 `uniq` 检查，手动删除重复段落

### KPI 不足
**症状:** 角色<3 个 KPI  
**修复:** 补充数据源，重新生成该角色

### 数据源缺失
**症状:** 引用<3 个数据源  
**修复:** 搜索 YouTube transcript + 在线数据

---

**文档保存位置:** `~/gemini/MiroFish/MiroFish_v3.0_Specification.md`  
**其他 Agent 可执行:** 所有步骤都是 CLI 命令，可复制粘贴执行
