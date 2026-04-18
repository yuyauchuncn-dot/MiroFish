#!/usr/bin/env python3
"""
MiroFish v3.0 YouTube 自动分析 - 报告生成器 (带并行处理和日志)
调用 LLM + Tavily 搜索生成 MiroFish v3.0 报告。
按 Ctrl+C (ESC) 可安全中断，自动保存进度。
"""

import json
import sys
import argparse
import logging
import signal
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import time

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from tavily import TavilyClient
    TAVILY_AVAILABLE = True
except ImportError:
    TAVILY_AVAILABLE = False

from config import (
    ENABLED, BAILIAN_API_KEY, BAILIAN_BASE_URL, BAILIAN_MODEL,
    TAVILY_API_KEY, TAVILY_MAX_RESULTS,
    YOUTUBE_DIR, TRANSCRIPTS_DIR, REPORTS_DIR, CHECKLIST_PATH, MIROFISH_SPEC_PATH,
    REPORT_DATE_FORMAT, REPORT_FILENAME_TEMPLATE
)

# 社交媒体模块（可选，按需加载）
def _load_social_config():
    import importlib.util, sys as _sys
    social_config_path = Path(__file__).parent.parent / "social-media" / "config.py"
    if not social_config_path.exists():
        return None
    spec = importlib.util.spec_from_file_location("social_config", social_config_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_SOCIAL_CFG = _load_social_config()
SOCIAL_MODULE_AVAILABLE = _SOCIAL_CFG is not None
SOCIAL_MEDIA_RAW_DIR = getattr(_SOCIAL_CFG, "SOCIAL_MEDIA_RAW_DIR", None)
SOCIAL_MEDIA_REPORTS_DIR = getattr(_SOCIAL_CFG, "SOCIAL_MEDIA_REPORTS_DIR", None)
SOCIAL_ENTITY_MAP = getattr(_SOCIAL_CFG, "SOCIAL_ENTITY_MAP", {})
TWITTER_ACCOUNTS = getattr(_SOCIAL_CFG, "TWITTER_ACCOUNTS", {})
SOCIAL_CHECKLIST_PATH = getattr(_SOCIAL_CFG, "CHECKLIST_PATH", None)

# 市场情绪分析模块（可选，按需加载）
def _load_sentiment_module(module_name):
    """动态加载 prototype 目录下的心模块"""
    proto_path = Path(__file__).parent.parent.parent / "livenews" / "prototype"
    module_path = proto_path / f"{module_name}.py"
    if not module_path.exists():
        return None
    spec = __import__("importlib").util.spec_from_file_location(module_name, module_path)
    mod = __import__("importlib").util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _format_sentiment_for_prompt(analysis) -> str:
    """将情绪分析结果格式化为 LLM 可读的 prompt 文本"""
    if not analysis or not analysis.keywords:
        return ""

    # 计算情绪标签
    score = analysis.overall_sentiment
    label = "强烈看涨" if score > 0.5 else ("看涨" if score > 0.2 else
           ("看跌" if score < -0.2 else "强烈看跌" if score < -0.5 else "中立"))

    lines = [
        "## 市场情绪分析（预分析数据）",
        f"- 整体情绪评分: {score:+.3f}",
        f"- 情绪标签: {label}",
        "",
        "### 关键词情绪评分",
    ]
    for kw, data in sorted(analysis.keywords.items(), key=lambda x: abs(x[1].sentiment), reverse=True):
        lines.append(f"- {kw} ({data.category}): {data.sentiment:+.3f}")
    return "\n".join(lines)

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(Path(REPORTS_DIR).parent / "mirofish_generation.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 全局标志：用于优雅中断
_shutdown_requested = False

def _signal_handler(signum, frame):
    """处理 Ctrl+C / SIGINT 信号"""
    global _shutdown_requested
    _shutdown_requested = True
    print("\n")
    logger.warning("📌 收到中断信号，正在安全关闭...")
    sys.exit(130)

# 注册信号处理器
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

# 并行处理配置
MAX_PARALLEL_JOBS = 3

class ChecklistManager:
    """管理 checklist.json 的读写"""

    def __init__(self, checklist_path=CHECKLIST_PATH):
        self.checklist_path = Path(checklist_path)

    def load(self):
        """读取 checklist.json"""
        if self.checklist_path.exists():
            with open(self.checklist_path) as f:
                return json.load(f)
        return {"enabled": ENABLED, "videos": {}}

    def save(self, data):
        """保存 checklist.json"""
        data["last_scanned"] = datetime.now().isoformat()
        with open(self.checklist_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def update_video_status(self, video_id, status, report_path=None):
        """更新单个视频的状态"""
        checklist = self.load()
        if video_id in checklist.get("videos", {}):
            checklist["videos"][video_id]["report_status"] = status
            if report_path:
                checklist["videos"][video_id]["report_path"] = report_path
            checklist["videos"][video_id]["processed_at"] = datetime.now().isoformat()
            self.save(checklist)
        return checklist["videos"].get(video_id)


def _apply_asr_corrections(text: str) -> str:
    """应用 ASR 错别字修正到文本"""
    try:
        import importlib.util
        fix_module = Path(__file__).parent.parent.parent / "evidence" / "fix_asr_errors.py"
        if fix_module.exists():
            spec = importlib.util.spec_from_file_location("fix_asr_errors", fix_module)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            corrections = getattr(mod, "ASR_CORRECTIONS", {})
            for wrong, correct in corrections.items():
                text = text.replace(wrong, correct)
    except Exception:
        pass
    return text


def store_tavily_to_db(tavily_data: dict, video_id: str, title: str) -> int:
    """将 Tavily 搜索结果持久化到 Evidence news DB

    Args:
        tavily_data: fetch_tavily_counterpoints() 返回值
        video_id: 视频 ID
        title: 视频标题

    Returns:
        实际插入条数
    """
    if not tavily_data or not tavily_data.get("results"):
        return 0

    try:
        import importlib.util, time, json as _json
        from evidence.config import NEWS_DB
        evidence_path = Path(__file__).parent.parent.parent / "evidence" / "db_schema.py"
        if not evidence_path.exists():
            return 0
        spec = importlib.util.spec_from_file_location("db_schema", evidence_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        EvidenceDB = mod.EvidenceDB
        UnifiedNewsSchema = mod.UnifiedNewsSchema
        new_id = mod.new_id
        content_hash = mod.content_hash
    except Exception:
        return 0

    query = f"{title} criticism alternative perspective"
    fetched_at = int(time.time())
    items = []

    # Store Tavily AI answer as a summary item
    if tavily_data.get("answer"):
        answer = tavily_data["answer"]
        items.append({
            "id": f"tavily_{new_id()[:12]}",
            "source": "tavily.search",
            "source_type": "api",
            "title": f"[Tavily] {title}",
            "content": answer,
            "url": "",
            "author": "tavily",
            "published_at": fetched_at,
            "fetched_at": fetched_at,
            "content_hash": content_hash(answer),
            "language": "en",
            "importance": 1,
            "raw_json": _json.dumps({
                "query": query,
                "video_id": video_id,
                "answer": answer,
                "result_count": len(tavily_data["results"]),
            }, ensure_ascii=False),
        })

    # Store each Tavily result as a separate news item
    for r in tavily_data.get("results", []):
        content = r.get("snippet", "")
        if not content:
            continue
        items.append({
            "id": f"tavily_{new_id()[:12]}",
            "source": "tavily.result",
            "source_type": "api",
            "title": r.get("title", ""),
            "content": content,
            "url": r.get("url", ""),
            "author": r.get("source", "tavily"),
            "published_at": fetched_at,
            "fetched_at": fetched_at,
            "content_hash": content_hash(content),
            "language": "en",
            "importance": 1,
            "raw_json": _json.dumps({
                "query": query,
                "video_id": video_id,
                "source": r.get("source"),
                "url": r.get("url"),
            }, ensure_ascii=False),
        })

    try:
        with EvidenceDB(NEWS_DB) as db:
            news_schema = UnifiedNewsSchema(db)
            count = news_schema.insert_batch(items)
            if count > 0:
                logger.info(f"Tavily 新闻已入库: {count} 条 (video: {video_id})")
            return count
    except Exception as e:
        logger.warning(f"Tavily 入库失败: {e}")
        return 0


def load_transcript(video_id, full_name, channel=None):
    """读取视频的字幕文件 (标准命名：full_name [video_id].txt)

    检查多个位置：
    1. 频道目录（和视频文件同目录）
    2. transcripts/ 目录
    3. YOUTUBE_DIR 根目录
    支持 .txt、.vtt 和 .srt 格式
    """
    # If full_name already ends with [video_id], don't add it again
    if full_name.endswith(f'[{video_id}]'):
        transcript_name = f"{full_name}.txt"
        vtt_name = f"{full_name}.vtt"
        srt_name = f"{full_name}.srt"
    else:
        transcript_name = f"{full_name} [{video_id}].txt"
        vtt_name = f"{full_name} [{video_id}].vtt"
        srt_name = f"{full_name} [{video_id}].srt"

    # 要检查的目录列表
    search_dirs = []

    # 添加频道目录（和视频文件同目录）
    if channel and channel != "Unknown":
        search_dirs.append(Path(YOUTUBE_DIR) / channel)

    # 添加 transcripts 目录（旧位置，youtube_downloads/transcripts/）
    search_dirs.append(Path(YOUTUBE_DIR) / "transcripts")

    # 添加 monodata/raw/youtube/ 目录（新位置，含频道子目录）
    if channel and channel != "Unknown":
        search_dirs.append(Path(TRANSCRIPTS_DIR) / channel)
    search_dirs.append(Path(TRANSCRIPTS_DIR))

    # 添加根目录
    search_dirs.append(Path(YOUTUBE_DIR))

    # 先找 .txt 文件
    for search_dir in search_dirs:
        transcript_file = search_dir / transcript_name
        if transcript_file.exists():
            with open(transcript_file, encoding="utf-8") as f:
                text = f.read()
                return _apply_asr_corrections(text)

    # 如果没有 .txt，尝试 .vtt 文件（需要清理 VTT 标签）
    for search_dir in search_dirs:
        vtt_file = search_dir / vtt_name
        if vtt_file.exists():
            logger.info(f"[{video_id}] 找到 .vtt 字幕文件，转换为纯文本")
            text = convert_vtt_to_text(vtt_file)
            return _apply_asr_corrections(text)

    # 如果没有 .vtt，尝试 .srt 文件（需要清理 SRT 标签）
    for search_dir in search_dirs:
        srt_file = search_dir / srt_name
        if srt_file.exists():
            logger.info(f"[{video_id}] 找到 .srt 字幕文件，转换为纯文本")
            text = convert_srt_to_text(srt_file)
            return _apply_asr_corrections(text)

    logger.warning(f"字幕文件不存在：{transcript_name} 或 {vtt_name} 或 {srt_name}")
    return None


def convert_vtt_to_text(vtt_path):
    """将 VTT 字幕文件转换为纯文本"""
    with open(vtt_path, encoding="utf-8") as f:
        vtt_content = f.read()

    # 移除 WEBVTT 头部
    lines = vtt_content.split('\n')
    text_lines = []
    in_header = True
    current_cue_text = []

    for line in lines:
        # 跳过 WEBVTT 头部
        if line.startswith('WEBVTT'):
            continue
        if in_header:
            if line.strip() == '':
                in_header = False
            continue

        # 跳过时间戳行和空行
        if re.match(r'^\d{2}:\d{2}:\d{2}', line) or line.strip() == '':
            if current_cue_text:
                text_lines.append(' '.join(current_cue_text))
                current_cue_text = []
            continue

        # 跳过样式和元数据
        if line.startswith('Kind:') or line.startswith('Language:') or line.startswith('NOTE'):
            continue

        # 收集字幕文本
        current_cue_text.append(line.strip())

    # 处理最后一段
    if current_cue_text:
        text_lines.append(' '.join(current_cue_text))

    # 清理 HTML 标签（如 <c>, </c>, <v>, </v> 等）
    text = '\n'.join(text_lines)
    text = re.sub(r'<[^>]+>', '', text)

    return text


def convert_srt_to_text(srt_path):
    """将 SRT 字幕文件转换为纯文本"""
    with open(srt_path, encoding="utf-8") as f:
        srt_content = f.read()

    # SRT 格式: 序号\n时间戳\n字幕文本\n空行
    text_lines = []
    lines = srt_content.split('\n')

    for line in lines:
        # 跳过序号行（纯数字）
        if line.strip().isdigit():
            continue
        # 跳过时间戳行（HH:MM:SS,mmm --> HH:MM:SS,mmm）
        if '-->' in line:
            continue
        # 跳过空行
        if line.strip() == '':
            continue
        # 收集字幕文本
        text_lines.append(line.strip())

    text = '\n'.join(text_lines)

    return text


def load_mirofish_spec():
    """读取 MiroFish v3.0 specification"""
    if Path(MIROFISH_SPEC_PATH).exists():
        with open(MIROFISH_SPEC_PATH, encoding="utf-8") as f:
            return f.read()
    return None


def load_social_content(handle: str) -> str | None:
    """读取指定 Twitter 账户的 cleaned text 文件（供报告生成使用）"""
    if not SOCIAL_MEDIA_RAW_DIR:
        return None
    cleaned_dir = Path(SOCIAL_MEDIA_RAW_DIR) / "twitter" / handle / "cleaned"
    if not cleaned_dir.exists():
        return None
    files = sorted(cleaned_dir.glob(f"{handle}_*.txt"), reverse=True)
    if not files:
        return None
    with open(files[0], encoding="utf-8") as f:
        return f.read()


def load_podcast_content(podcast_id: str) -> str | None:
    """读取指定小宇宙播客的最新 cleaned text 文件"""
    if not SOCIAL_MEDIA_RAW_DIR:
        return None
    cleaned_dir = Path(SOCIAL_MEDIA_RAW_DIR) / "xiaoyuzhoufm" / podcast_id / "cleaned"
    if not cleaned_dir.exists():
        return None
    files = sorted(cleaned_dir.glob("*_cleaned.txt"), reverse=True)
    if not files:
        return None
    with open(files[0], encoding="utf-8") as f:
        return f.read()


def find_social_context_for_text(text: str) -> str:
    """
    从文本（字幕/内容）中检测关键实体，查找对应社交媒体数据并返回上下文。
    Fast path: 关键词匹配，零额外 API 成本。
    """
    if not SOCIAL_ENTITY_MAP or not text:
        return ""

    matched_sources = []
    seen_handles = set()

    for keyword, sources in SOCIAL_ENTITY_MAP.items():
        if keyword.lower() in text.lower():
            for source in sources:
                platform, handle = source.split(":", 1)
                if handle in seen_handles:
                    continue
                seen_handles.add(handle)
                if platform == "twitter":
                    content = load_social_content(handle)
                    if content:
                        logger.info(f"找到 @{handle} 的社交数据，注入到报告上下文")
                        matched_sources.append(content[:3000])  # 每个账户最多 3000 字符

    return "\n\n---\n\n".join(matched_sources)


def fetch_tavily_counterpoints(topic, max_results=TAVILY_MAX_RESULTS):
    """从 Tavily 搜索反方观点和相关新闻"""
    if not TAVILY_AVAILABLE or not TAVILY_API_KEY:
        return None

    try:
        client = TavilyClient(api_key=TAVILY_API_KEY)
        response = client.search(
            query=f"{topic} criticism alternative perspective",
            max_results=max_results,
            include_answer=True
        )

        search_results = []
        for result in response.get("results", []):
            search_results.append({
                "title": result.get("title"),
                "url": result.get("url"),
                "snippet": result.get("snippet"),
                "source": result.get("source")
            })

        return {
            "answer": response.get("answer"),
            "results": search_results
        }
    except Exception as e:
        logger.warning(f"Tavily 搜索失败: {e}")
        return None


def generate_report_with_bailian(video_id, title, transcript, spec, tavily_data,
                                  source_type="youtube", social_context="",
                                  sentiment_context=""):
    """使用百炼 LLM 生成 MiroFish v3.0 报告"""

    if not OPENAI_AVAILABLE:
        logger.error("OpenAI 库未安装")
        return None

    if not BAILIAN_API_KEY:
        logger.error("未配置 BAILIAN_API_KEY")
        return None

    try:
        client = OpenAI(
            api_key=BAILIAN_API_KEY,
            base_url=BAILIAN_BASE_URL
        )

        # 构造 system prompt
        tavily_context = ""
        if tavily_data and tavily_data.get("results"):
            tavily_context = f"""
## 来自 Tavily 搜索的反方观点和背景信息

### 搜索摘要
{tavily_data.get('answer', '无摘要')}

### 相关新闻源 (最近5条)
"""
            for i, result in enumerate(tavily_data.get("results", [])[:5], 1):
                snippet = result.get('snippet') or 'N/A'
                tavily_context += f"""
{i}. **{result.get('title', 'N/A')}**
   来源: {result.get('source', 'N/A')}
   摘要: {snippet[:200] if snippet != 'N/A' else 'N/A'}...
   链接: {result.get('url', 'N/A')}
"""

        system_prompt = f"""你是一位专业的投资分析师，需要为以下{'YouTube 视频' if source_type == 'youtube' else '社交媒体'}内容生成 MiroFish v3.0 格式的深度分析报告。

## MiroFish v3.0 规范
{spec}

## 反方观点和背景资料
{tavily_context if tavily_context else "无搜索到的反方观点资料"}
{f'''
## 社交媒体上下文（相关人物/机构的近期动态）
{social_context}

请结合以上社交媒体数据，在报告末尾增加 **Persona Analysis（人物画像）** 章节，分析相关人物/机构的立场、发言模式和市场影响力。
''' if social_context else ""}
{f'''
## 市场情绪分析（预分析数据）
{sentiment_context}

各动态角色请结合以上情绪评分进行投资决策分析。
''' if sentiment_context else ""}
## 生成要求
1. 必须包含 Executive Summary (1000-1500 字)
2. 必须包含 6 个动态角色分析 (每个≥500字，每个≥3个KPI)
3. 必须包含 Entity Extraction 表格
4. 必须包含 Risk Assessment Matrix (4x4)
5. 必须包含 Final Decision (3+ 建议)
6. 必须包含 Personal Positioning
7. 必须包含 KPI Verification Log
8. 避免重复内容
9. 使用中文撰写
10. 如有 Tavily 搜索结果，请引用作为反方观点支撑材料
11. 每个 Dynamic Role 必须充分展开论述，展示完整的分析逻辑、数据支撑和投资建议，不得因篇幅压缩而省略关键 KPI 或分析深度
"""

        user_prompt = f"""基于以下{'YouTube 视频的字幕' if source_type == 'youtube' else '社交媒体'}内容，生成完整的 MiroFish v3.0 分析报告。

**{'视频标题' if source_type == 'youtube' else '账户/主题'}**: {title}

**内容**:
{transcript[:12000]}

请按 MiroFish v3.0 规范生成完整报告。"""

        # 调用 LLM
        logger.info(f"调用百炼 LLM (model: {BAILIAN_MODEL})...")
        response = client.chat.completions.create(
            model=BAILIAN_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=8192
        )

        report_content = response.choices[0].message.content
        return report_content

    except Exception as e:
        logger.error(f"LLM 生成失败: {e}", exc_info=True)
        return None


# ── Entity graph ingestion hook ────────────────────────────────────

_ERW_INGEST_SCRIPT = Path(__file__).resolve().parent.parent.parent / "entityrelationshipweb" / "ingest_mirofish_reports.py"


def _entity_graph_ingest(report_path: str):
    """Call entityrelationshipweb ingest script to store report knowledge in DB.

    Runs as subprocess to avoid import conflicts (different Python envs).
    Fails silently — ingestion errors never break report generation.
    """
    if not _ERW_INGEST_SCRIPT.exists():
        logger.debug(f"Entity graph ingest script not found: {_ERW_INGEST_SCRIPT}")
        return

    result = subprocess.run(
        [sys.executable, str(_ERW_INGEST_SCRIPT), "--single", report_path],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode == 0:
        output = result.stdout.strip()
        if output:
            logger.info(f"Entity graph ingest: {output}")
    else:
        stderr = result.stderr.strip().split("\n")[-1] if result.stderr else "unknown"
        logger.warning(f"Entity graph ingest failed for {Path(report_path).name}: {stderr}")


# ── Market intelligence ingestion hook ─────────────────────────────

_MONODATA_INGEST_SCRIPT = Path(__file__).resolve().parent.parent.parent / "monodata" / "scripts" / "ingest_mirofish_reports.py"


def _market_intelligence_ingest(report_path: str):
    """Call monodata ingest script to store report analysis + causal edges in DB.

    Runs as subprocess to avoid import conflicts.
    Fails silently — ingestion errors never break report generation.
    """
    if not _MONODATA_INGEST_SCRIPT.exists():
        logger.debug(f"Market intelligence ingest script not found: {_MONODATA_INGEST_SCRIPT}")
        return

    result = subprocess.run(
        [sys.executable, str(_MONODATA_INGEST_SCRIPT), "--single", report_path],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode == 0:
        output = result.stdout.strip()
        if output:
            logger.info(f"Market intelligence ingest: {output}")
    else:
        stderr = result.stderr.strip().split("\n")[-1] if result.stderr else "unknown"
        logger.warning(f"Market intelligence ingest failed for {Path(report_path).name}: {stderr}")


def sanitize_filename(filename: str) -> str:
    """清理文件名中的非法字符（特别是处理中文特殊字符如 /）"""
    # 替换 / 为 - (常见的非法文件名字符)
    filename = filename.replace("/", " - ").replace("\\", " - ")
    # 移除其他操作系统非法字符
    illegal_chars = [':', '*', '?', '"', '<', '>', '|']
    for char in illegal_chars:
        filename = filename.replace(char, " ")
    return filename.strip()


def generate_v4_report(
    video_id, channel_name, full_name, title, source_type="youtube",
    social_context="", sentiment_context="", tavily_data=None,
    force_topic=None, force_topic_suffix=None,
    transcript_text=None,  # For article/local_txt: pre-loaded text content
):
    """使用 v4 辩论引擎 + 本地 DB 生成报告 — 通过统一注册表调用"""
    logger.info(f"[{video_id}] 开始生成 v4 报告: {title[:50]}...")
    start_time = time.time()

    # 读取内容
    if transcript_text:
        # Pre-loaded content (e.g., from monofetchers or local .txt)
        transcript = transcript_text
    elif source_type == "social-media":
        transcript = load_social_content(video_id)
    elif source_type == "podcast":
        transcript = load_podcast_content(video_id)
    else:
        transcript = load_transcript(video_id, full_name, channel_name)

    if not transcript:
        logger.error(f"[{video_id}] v4: 内容不存在")
        return None

    logger.info(f"[{video_id}] v4: 内容长度 {len(transcript)} 字符")

    # 通过注册表调用 v4 生成器
    try:
        _src_path = str(Path(__file__).parent.parent / "src")
        sys.path.insert(0, _src_path)
        from registry import get_generator
        gen = get_generator("v4")
        result = gen.generate(
            transcript=transcript,
            title=title,
            video_id=video_id,
            channel=channel_name,
            social_context=social_context,
            sentiment_context=sentiment_context,
            tavily_data=tavily_data,
        )
    except Exception as e:
        logger.error(f"[{video_id}] v4 报告生成失败: {e}", exc_info=True)
        return None
    finally:
        if _src_path in sys.path:
            sys.path.remove(_src_path)

    if not result:
        logger.error(f"[{video_id}] v4: 返回结果为空")
        return None

    elapsed = time.time() - start_time
    report_path = result.get("report_path", "")
    report_content = result.get("report_content", "")
    logger.info(
        f"[{video_id}] v4 报告生成成功! 耗时: {elapsed:.1f}s, "
        f"报告长度: {len(report_content)} 字符"
    )

    # 提取预测到跟踪文件
    if report_content:
        try:
            extract_script = Path(__file__).parent.parent.parent / "scripts" / "predictions" / "extract_predictions.py"
            if extract_script.exists():
                import importlib.util
                spec = importlib.util.spec_from_file_location("extract_predictions", extract_script)
                ext_mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(ext_mod)
                predictions = ext_mod.extract_predictions_from_report(report_content, report_id=video_id)
                if predictions:
                    existing = ext_mod.load_tracking()
                    existing_ids = {p["id"] for p in existing}
                    new_count = sum(1 for p in predictions if p["id"] not in existing_ids)
                    for p in predictions:
                        if p["id"] not in existing_ids:
                            existing.append(p)
                    ext_mod.save_tracking(existing)
                    logger.info(f"[{video_id}] 预测已跟踪: {new_count} 个新预测")
        except Exception as e:
            logger.warning(f"[{video_id}] 预测提取失败: {e}")

    return report_path if report_path else None


def generate_report(video_id, channel_name, full_name, title, source_type="youtube", use_v4=False, transcript_text=None):
    """生成单个视频的 MiroFish 报告"""

    if use_v4:
        # v4 模式: 使用辩论引擎 + 本地 DB
        tavily_data = fetch_tavily_counterpoints(title)
        store_tavily_to_db(tavily_data, video_id, title)
        social_context = ""
        if source_type == "youtube":
            transcript_tmp = transcript_text or load_transcript(video_id, full_name, channel_name) or ""
            social_context = find_social_context_for_text(transcript_tmp)

        sentiment_context = ""
        try:
            sentiment_mod = _load_sentiment_module("keyword_sentiment_analyzer")
            transcript_tmp = transcript_text or load_transcript(video_id, full_name, channel_name) or ""
            if sentiment_mod and transcript_tmp:
                analyzer = sentiment_mod.KeywordSentimentAnalyzer(use_llm=True)
                analysis = analyzer.analyze_report_content(
                    report_text=transcript_tmp, use_llm=True, max_keywords=3
                )
                sentiment_context = _format_sentiment_for_prompt(analysis)
        except Exception as e:
            logger.warning(f"[{video_id}] 情绪预分析失败: {e}")

        return generate_v4_report(
            video_id, channel_name, full_name, title, source_type,
            social_context, sentiment_context, tavily_data,
            transcript_text=transcript_text,
        )

    logger.info(f"[{video_id}] 开始生成报告: {title[:50]}...")
    start_time = time.time()

    # 读取内容（优先使用预加载的 transcript_text，否则从文件系统加载）
    if transcript_text:
        transcript = transcript_text
    elif source_type == "social-media":
        transcript = load_social_content(video_id)
        if not transcript:
            logger.error(f"[{video_id}] 社交媒体 cleaned text 不存在")
            return None
    elif source_type == "podcast":
        transcript = load_podcast_content(video_id)
        if not transcript:
            logger.error(f"[{video_id}] 播客 cleaned text 不存在")
            return None
    else:
        transcript = load_transcript(video_id, full_name, channel_name)
        if not transcript:
            logger.error(f"[{video_id}] 字幕文件不存在")
            return None

    logger.info(f"[{video_id}] 内容长度: {len(transcript)} 字符")

    # 读取规范
    spec = load_mirofish_spec()
    if not spec:
        logger.error(f"[{video_id}] MiroFish 规范文件不存在")
        return None

    # 从 Tavily 获取反方观点
    logger.info(f"[{video_id}] 搜索 Tavily 反方观点...")
    tavily_data = fetch_tavily_counterpoints(title)
    store_tavily_to_db(tavily_data, video_id, title)
    if tavily_data:
        logger.info(f"[{video_id}] 找到 {len(tavily_data['results'])} 条相关新闻")
    else:
        logger.info(f"[{video_id}] Tavily 搜索无结果或已禁用")

    # 查找社交媒体上下文（实体关键词匹配）
    social_context = ""
    if source_type == "youtube":
        social_context = find_social_context_for_text(transcript)
        if social_context:
            logger.info(f"[{video_id}] 注入社交媒体上下文 ({len(social_context)} 字符)")

    # === Stage 1: 预分析市场情绪（LLM 分析整体 + Top 3 关键词）===
    sentiment_context = ""
    try:
        sentiment_mod = _load_sentiment_module("keyword_sentiment_analyzer")
        if sentiment_mod:
            analyzer = sentiment_mod.KeywordSentimentAnalyzer(use_llm=True)
            analysis = analyzer.analyze_report_content(
                report_text=transcript,
                use_llm=True,
                max_keywords=3  # 仅 LLM 分析 Top 3 关键词，其余用启发式
            )
            sentiment_context = _format_sentiment_for_prompt(analysis)
            if sentiment_context:
                logger.info(f"[{video_id}] 情绪预分析完成（LLM Top 3 + 启发式）: {len(analysis.keywords)} 关键词, 整体={analysis.overall_sentiment:+.3f}")
    except Exception as e:
        logger.warning(f"[{video_id}] 情绪预分析失败: {e}")

    # 调用 LLM 生成报告
    report_content = generate_report_with_bailian(
        video_id, title, transcript, spec, tavily_data,
        source_type=source_type, social_context=social_context,
        sentiment_context=sentiment_context,
    )
    if not report_content:
        logger.error(f"[{video_id}] 报告生成失败")
        return None

    # 确定报告保存目录（社交媒体报告存到不同路径）
    if source_type in ("social-media", "podcast") and SOCIAL_MEDIA_REPORTS_DIR:
        subdir = "twitter" if source_type == "social-media" else "xiaoyuzhoufm"
        report_dir = Path(SOCIAL_MEDIA_REPORTS_DIR) / subdir / channel_name
    else:
        report_dir = Path(REPORTS_DIR) / channel_name
    report_dir.mkdir(parents=True, exist_ok=True)

    # 报告命名: {date}_{video_id}_{short_title}_MiroFish.md
    date_str = datetime.now().strftime("%Y%m%d")
    short_title = sanitize_filename(title)[:40].strip()
    report_filename = f"{date_str}_{video_id}_{short_title}_MiroFish.md"
    logger.info(f"[{video_id}] 报告文件名: {report_filename}")
    report_path = report_dir / report_filename

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    # === Stage 3: 追加情绪摘要 + 保存 JSON sidecar（LLM，Top 10 关键词）===
    try:
        integration_mod = _load_sentiment_module("mirofish_bailian_integration")
        if integration_mod:
            integrator = integration_mod.MiroFishBailianIntegrator(use_llm=True)
            enhanced = integrator.add_sentiment_analysis(report_content, title, max_keywords=10)
            sentiment_summary = integrator.generate_sentiment_summary(enhanced["sentiment_analysis"], top_n=5)
            # 追加到报告末尾
            with open(report_path, "a", encoding="utf-8") as f:
                f.write("\n\n" + sentiment_summary)
            # 保存 JSON sidecar
            sentiment_filename = sanitize_filename(f"{date_str}_{full_name}_Sentiment.json")
            sentiment_path = report_dir / sentiment_filename
            integrator.save_enhanced_report(enhanced, str(sentiment_path))
            logger.info(f"[{video_id}] 情绪分析已追加: {len(enhanced['sentiment_analysis']['keyword_sentiments'])} 关键词, JSON: {sentiment_path}")
    except Exception as e:
        logger.warning(f"[{video_id}] 情绪后处理失败: {e}")

    # === Stage 4: 入库到 entity_graph.db ===
    try:
        _entity_graph_ingest(str(report_path))
    except Exception as e:
        logger.warning(f"[{video_id}] 报告入库失败（不影响报告生成）: {e}")

    # === Stage 5: 入库到 market_intelligence.db + 因果边 ===
    try:
        _market_intelligence_ingest(str(report_path))
    except Exception as e:
        logger.warning(f"[{video_id}] 市场情报入库失败（不影响报告生成）: {e}")

    return str(report_path)


def transcript_exists(video_id, full_name, channel=None):
    """Check if transcript file exists (standard naming: full_name [video_id].txt)

    Check in multiple locations:
    1. Channel directory (same as video file)
    2. Central transcripts directory
    3. YOUTUBE_DIR root
    Support both .txt and .vtt formats
    """
    # If full_name already ends with [video_id], don't add it again
    if full_name.endswith(f'[{video_id}]'):
        transcript_name = f"{full_name}.txt"
        vtt_name = f"{full_name}.vtt"
    else:
        transcript_name = f"{full_name} [{video_id}].txt"
        vtt_name = f"{full_name} [{video_id}].vtt"

    # Build search directories list
    search_dirs = []

    # Add channel directory
    if channel and channel != "Unknown":
        search_dirs.append(Path(YOUTUBE_DIR) / channel)

    # Add transcripts directory
    search_dirs.append(Path(YOUTUBE_DIR) / "transcripts")

    # Add root directory
    search_dirs.append(Path(YOUTUBE_DIR))

    # Check for .txt file
    for search_dir in search_dirs:
        if (search_dir / transcript_name).exists():
            return True

    # Check for .vtt file
    for search_dir in search_dirs:
        if (search_dir / vtt_name).exists():
            return True

    return False


def process_pending_videos(max_parallel=MAX_PARALLEL_JOBS, use_v4=False):
    """处理所有待处理的视频，支持并行处理"""

    logger.info(f"\n{'='*70}")
    if use_v4:
        logger.info("🚀 开始批量生成 v4 报告 (并行处理)")
    else:
        logger.info("🚀 开始批量生成报告 (并行处理)")
    logger.info(f"{'='*70}")

    manager = ChecklistManager()
    checklist = manager.load()

    # 收集待处理视频（包括 pending 和 error 状态）
    pending_videos = []
    updated_count = 0

    for video_id, info in checklist.get("videos", {}).items():
        report_status = info.get("report_status")

        # 只处理有字幕且状态为 pending 或 error 的视频
        if not info.get("has_transcript", False):
            continue

        if report_status not in ("pending", "error"):
            continue

        # 重新验证字幕文件是否存在（支持多种命名模式）
        full_name = info.get("full_name")
        channel = info.get("channel")

        if not transcript_exists(video_id, full_name, channel):
            logger.warning(f"[{video_id}] 字幕文件不存在，更新状态为 no_transcript")
            checklist["videos"][video_id]["has_transcript"] = False
            checklist["videos"][video_id]["report_status"] = "no_transcript"
            updated_count += 1
            continue

        # 更新 has_transcript 标志（如果之前是 false）
        if not info.get("has_transcript", False):
            checklist["videos"][video_id]["has_transcript"] = True
            updated_count += 1

        pending_videos.append({
            "video_id": video_id,
            "full_name": full_name,
            "channel": info.get("channel"),
            "title": info.get("full_name", "Unknown")  # 使用 full_name 作为标题
        })

    # 保存更新的 checklist
    if updated_count > 0:
        manager.save(checklist)
        logger.info(f"更新了 {updated_count} 个视频的状态")

    if not pending_videos:
        logger.info("没有待处理的视频")
        return

    logger.info(f"发现 {len(pending_videos)} 个待处理视频")
    logger.info(f"设置并行处理数: {max_parallel}")

    success_count = 0
    error_count = 0
    start_time = time.time()

    # 使用线程池并行处理
    with ThreadPoolExecutor(max_workers=max_parallel) as executor:
        # 提交所有任务
        future_to_video = {
            executor.submit(
                generate_report,
                video["video_id"],
                video["channel"],
                video["full_name"],
                video["title"],
                "youtube",
                use_v4,
            ): video for video in pending_videos
        }

        # 收集结果
        for future in as_completed(future_to_video):
            video = future_to_video[future]
            video_id = video["video_id"]

            try:
                report_path = future.result()
                if report_path:
                    manager.update_video_status(video_id, "done", report_path)
                    success_count += 1
                else:
                    manager.update_video_status(video_id, "error")
                    error_count += 1
            except Exception as e:
                logger.error(f"[{video_id}] 处理失败: {e}", exc_info=True)
                manager.update_video_status(video_id, "error")
                error_count += 1

    elapsed = time.time() - start_time
    logger.info(f"\n{'='*70}")
    logger.info("📊 批量处理完成")
    logger.info(f"{'='*70}")
    logger.info(f"✅ 成功: {success_count}")
    logger.info(f"❌ 失败: {error_count}")
    logger.info(f"⏱️  总耗时: {elapsed:.1f}s ({elapsed/max(1, success_count + error_count):.1f}s/个)")
    logger.info(f"{'='*70}\n")


def test_single_video(video_id, use_v4=False, transcript_text=None):
    """测试单个视频的报告生成"""

    logger.info(f"\n{'='*70}")
    if use_v4:
        logger.info("🧪 v4 测试模式: 生成单个视频报告 (多代理辩论 + 预测引擎)")
    else:
        logger.info(f"🧪 测试模式: 生成单个视频报告")
    logger.info(f"{'='*70}")

    manager = ChecklistManager()
    checklist = manager.load()
    videos = checklist.get("videos", {})

    if video_id not in videos:
        logger.warning(f"视频 ID '{video_id}' 不在 checklist 中，尝试从磁盘扫描...")
        # 磁盘扫描兜底：直接搜索 YOUTUBE_DIR 下的 .mp4 文件
        youtube_dir = Path(YOUTUBE_DIR)
        ignored_dir = youtube_dir / "ignored"
        found_info = None
        for mp4 in youtube_dir.rglob("*.mp4"):
            if not mp4.is_file():
                continue
            if ignored_dir in mp4.parents:
                continue
            m = re.search(r'\[([^\]]+)\]$', mp4.stem)
            if m and m.group(1) == video_id:
                # 推断 channel（第一级子目录名）
                try:
                    rel = mp4.relative_to(youtube_dir)
                    ch = rel.parts[0] if len(rel.parts) > 1 else "Unknown"
                except ValueError:
                    ch = "Unknown"
                date_m = re.match(r'^(\d{8})', mp4.stem)
                found_info = {
                    "full_name": mp4.stem,
                    "channel": ch,
                    "date": date_m.group(1) if date_m else datetime.now().strftime("%Y%m%d"),
                    "has_transcript": True,
                    "status": "pending",
                }
                logger.info(f"磁盘扫描找到视频: {mp4.stem} (频道: {ch})")
                break

        if found_info is None:
            logger.error(f"视频 ID '{video_id}' 不在 checklist 中，且磁盘扫描未找到对应文件")
            return False

        # 将找到的视频临时注入 checklist（仅内存，不写盘）
        videos[video_id] = found_info

    video_info = videos[video_id]
    full_name = video_info.get("full_name", "Unknown")
    title = full_name
    channel = video_info.get("channel", "Unknown")
    has_transcript = video_info.get("has_transcript", False)

    logger.info(f"📺 视频信息:")
    logger.info(f"   ID: {video_id}")
    logger.info(f"   标题: {title}")
    logger.info(f"   频道: {channel}")
    logger.info(f"   有字幕: {has_transcript}")

    # 如果有预加载的 transcript_text（来自 monofetchers），跳过字幕检查
    if not has_transcript and not transcript_text:
        logger.error(f"该视频没有字幕，无法生成报告")
        return False

    if transcript_text:
        logger.info(f"   使用预加载的 transcript: {len(transcript_text)} chars")

    # 生成报告
    report_path = generate_report(video_id, channel, full_name, title, use_v4=use_v4, transcript_text=transcript_text)

    if report_path:
        logger.info(f"✅ 报告生成成功")
        logger.info(f"   路径: {report_path}")

        # 验证报告格式
        with open(report_path, encoding="utf-8") as f:
            content = f.read()

        # v4 和 v3 有不同的格式检查
        if use_v4:
            checks = {
                "预测摘要": "预测摘要" in content,
                "多代理辩论": "多代理辩论" in content,
                "情景预测": "情景预测" in content,
                "行动建议": "行动建议" in content,
                "DB 数据验证": "DB 数据验证" in content or "DB 数据" in content,
            }
        else:
            checks = {
                "Executive Summary": "Executive Summary" in content or "执行摘要" in content,
                "6 Dynamic Roles": content.count("## ") >= 6,
                "Entity Extraction": "Entity Extraction" in content or "实体提取" in content,
                "Risk Assessment": "Risk Assessment" in content or "风险评估" in content,
                "Final Decision": "Final Decision" in content or "最终建议" in content,
            }

        logger.info(f"📋 格式检查:")
        for check_name, passed in checks.items():
            status = "✅" if passed else "❌"
            logger.info(f"   {status} {check_name}")

        return all(checks.values())
    else:
        logger.error(f"报告生成失败")
        return False


def generate_podcast_report(podcast_id: str, podcast_name: str = "") -> str | None:
    """为指定小宇宙播客生成 MiroFish 报告"""
    logger.info(f"\n{'='*70}")
    logger.info(f"生成播客报告: {podcast_name or podcast_id}")
    logger.info(f"{'='*70}")

    content = load_podcast_content(podcast_id)
    if not content:
        logger.error(f"[{podcast_id}] 找不到 cleaned text，请先运行 xiaoyuzhoufm_fetcher.py")
        return None

    title = podcast_name or podcast_id
    return generate_report(
        video_id=podcast_id,
        channel_name=podcast_id,
        full_name=title,
        title=title,
        source_type="podcast",
    )


def generate_social_report(handle: str) -> str | None:
    logger.info(f"\n{'='*70}")
    logger.info(f"生成社交媒体报告: @{handle}")
    logger.info(f"{'='*70}")

    content = load_social_content(handle)
    if not content:
        logger.error(f"[@{handle}] 找不到 cleaned text，请先运行 twitter_fetcher.py")
        return None

    account_info = TWITTER_ACCOUNTS.get(handle, {})
    display_name = account_info.get("display_name", handle)
    title = f"{display_name} (@{handle}) Twitter 分析"

    # 社交报告使用 handle 作为 channel，handle 作为 video_id
    return generate_report(
        video_id=handle,
        channel_name=handle,
        full_name=title,
        title=title,
        source_type="social-media",
    )


def main():
    parser = argparse.ArgumentParser(
        description="MiroFish v3.0 报告生成器"
    )
    parser.add_argument(
        "--test",
        type=str,
        help="测试模式：为指定视频 ID 生成报告"
    )
    parser.add_argument(
        "--process-all",
        action="store_true",
        help="处理所有待处理的视频 (并行处理)"
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=MAX_PARALLEL_JOBS,
        help=f"并行处理的最大任务数 (默认: {MAX_PARALLEL_JOBS})"
    )
    parser.add_argument(
        "--check-deps",
        action="store_true",
        help="检查依赖库"
    )
    parser.add_argument(
        "--source-type",
        choices=["youtube", "social-media", "podcast"],
        default="youtube",
        help="数据源类型 (默认: youtube)"
    )
    parser.add_argument(
        "--account",
        type=str,
        help="社交媒体账户名 (配合 --source-type social-media 使用)"
    )
    parser.add_argument(
        "--podcast-id",
        type=str,
        help="小宇宙播客 ID (配合 --source-type podcast 使用)"
    )
    parser.add_argument(
        "--podcast-name",
        type=str,
        default="",
        help="播客显示名称 (可选)"
    )
    parser.add_argument(
        "--v4",
        action="store_true",
        help="使用 MiroFish v4.0 框架 (多代理辩论 + 预测引擎)"
    )
    parser.add_argument(
        "--transcript-text-file",
        type=str,
        help="预加载的 transcript 文件路径（来自 monofetchers）"
    )

    args = parser.parse_args()

    if args.check_deps:
        logger.info("📦 依赖检查:")
        logger.info(f"   {'✅' if OPENAI_AVAILABLE else '❌'} OpenAI (openai)")
        logger.info(f"   {'✅' if TAVILY_AVAILABLE else '❌'} Tavily (tavily-python)")
        logger.info(f"   {'✅' if SOCIAL_MODULE_AVAILABLE else '❌'} 社交媒体模块")
        if not OPENAI_AVAILABLE or not TAVILY_AVAILABLE:
            logger.info("\n缺少依赖库，请运行:")
            logger.info("   pip install openai tavily-python")
        return

    if args.source_type == "podcast":
        if args.podcast_id:
            report_path = generate_podcast_report(args.podcast_id, args.podcast_name)
            sys.exit(0 if report_path else 1)
        else:
            logger.error("--source-type podcast 需要 --podcast-id <id>")
            sys.exit(1)
    elif args.source_type == "social-media":
        if args.account:
            report_path = generate_social_report(args.account)
            sys.exit(0 if report_path else 1)
        elif args.process_all:
            # 处理所有有内容但未生成报告的账户
            for handle in TWITTER_ACCOUNTS:
                content = load_social_content(handle)
                if content:
                    generate_social_report(handle)
        else:
            logger.error("--source-type social-media 需要 --account <handle> 或 --process-all")
            sys.exit(1)
    elif args.test:
        # Read pre-loaded transcript if provided
        transcript_text = None
        if args.transcript_text_file:
            try:
                transcript_text = Path(args.transcript_text_file).read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Failed to read transcript file: {e}")
        success = test_single_video(args.test, use_v4=args.v4, transcript_text=transcript_text)
        sys.exit(0 if success else 1)
    elif args.process_all:
        process_pending_videos(max_parallel=args.parallel, use_v4=args.v4)
    else:
        logger.info("Usage: python report_generator.py [OPTIONS]")
        logger.info("\nOptions:")
        logger.info("  --test <video_id>                  生成单个视频的测试报告")
        logger.info("  --v4                               使用 MiroFish v4.0 框架 (多代理辩论 + 预测引擎)")
        logger.info("  --process-all                      处理所有待处理的视频 (并行)")
        logger.info("  --parallel N                       设置并行处理数 (默认: 3)")
        logger.info("  --source-type social-media         使用社交媒体数据源")
        logger.info("  --account <handle>                 指定社交媒体账户")
        logger.info("  --check-deps                       检查依赖库")


if __name__ == "__main__":
    main()
