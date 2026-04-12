#!/usr/bin/env python3
"""MiroFish v3 报告生成器 — 经典 6 角色单作者报告"""

import os
import sys
from pathlib import Path
from typing import Optional

_MIROFISH_ROOT = Path(__file__).parent.parent.parent  # v3/ → src/ → mirofish/


class V3Generator:
    """v3 报告生成器 (archived — legacy)

    经典 v3 流程: transcript + spec + Tavily -> LLM -> 报告
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
        **kwargs,
    ) -> Optional[dict]:
        """生成 v3 报告

        v3 生成报告内容，但不自动保存文件。调用方负责保存。
        """
        try:
            sys.path.insert(0, str(_MIROFISH_ROOT / "youtube_pipeline"))
            from report_generator import generate_report_with_bailian, load_mirofish_spec

            spec = load_mirofish_spec()
            if not spec:
                return None

            content = generate_report_with_bailian(
                video_id=video_id,
                title=title,
                transcript=transcript,
                spec=spec,
                tavily_data=tavily_data,
                social_context=social_context,
                sentiment_context=sentiment_context,
            )

            if not content:
                return None

            return {"report_content": content, "report_path": ""}

        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"v3 报告生成失败: {e}", exc_info=True)
            return None
        finally:
            p = str(_MIROFISH_ROOT / "youtube_pipeline")
            if p in sys.path:
                sys.path.remove(p)
