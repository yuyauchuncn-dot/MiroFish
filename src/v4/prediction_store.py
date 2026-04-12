#!/usr/bin/env python3
"""MiroFish v4 预测存储引擎

管理预测的创建、存储、验证和校准统计。

核心功能:
- 预测记录写入 predictions.db
- 预测记分卡维护 (scorecard.json)
- Brier Score 和校准偏差计算
- 历史预测验证状态管理
"""

import json
import logging
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# monorepo 根目录 — prediction_store.py 在 src/v4/ 下
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
_PREDICTIONS_DIR = _MONO_ROOT / "monodata" / "reports" / "predictions"
_PREDICTIONS_DB = _PREDICTIONS_DIR / "predictions.db"
_SCORECARD_FILE = _PREDICTIONS_DIR / "scorecard.json"


@dataclass
class Prediction:
    """单条可验证预测"""
    prediction: str               # 具体预测内容
    trigger_condition: str        # 触发条件
    predicted_prob: float         # 预测概率 (0-1)
    verify_by: str                # 验证时间 (YYYY-MM-DD)
    agent: str                    # 哪个代理提出的
    report_id: str = ""           # 关联报告 ID
    tags: str = ""                # 标签: [geopolitics, market, ...]
    id: str = ""                  # 自动生成 UUID
    predicted_at: str = ""        # 自动填充
    actual_outcome: Optional[int] = None  # 1=命中, 0=未命中
    verified_at: str = ""         # 验证后自动填充

    def __post_init__(self):
        if not self.id:
            self.id = f"pred_{uuid.uuid4().hex[:12]}"
        if not self.predicted_at:
            self.predicted_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")


class PredictionStore:
    """预测存储引擎"""

    def __init__(self, db_path: str = None):
        db_path = Path(db_path) if db_path else _PREDICTIONS_DB
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(db_path)
        self._ensure_schema()

    def _ensure_schema(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS predictions (
                    id TEXT PRIMARY KEY,
                    report_id TEXT,
                    prediction TEXT,
                    trigger_condition TEXT,
                    predicted_prob REAL,
                    predicted_at TEXT,
                    verify_by TEXT,
                    actual_outcome INTEGER,
                    verified_at TEXT,
                    agent TEXT,
                    tags TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_predicted_at ON predictions(predicted_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_verify_by ON predictions(verify_by)
            """)

    def save(self, pred: Prediction) -> Prediction:
        """保存预测到数据库"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO predictions
                (id, report_id, prediction, trigger_condition, predicted_prob,
                 predicted_at, verify_by, actual_outcome, verified_at, agent, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pred.id, pred.report_id, pred.prediction, pred.trigger_condition,
                pred.predicted_prob, pred.predicted_at, pred.verify_by,
                pred.actual_outcome, pred.verified_at, pred.agent, pred.tags
            ))
        return pred

    def save_batch(self, predictions: List[Prediction]) -> int:
        """批量保存预测"""
        count = 0
        for pred in predictions:
            self.save(pred)
            count += 1
        return count

    def get_pending(self) -> List[Prediction]:
        """获取待验证的预测（verify_by 已到期但未验证）"""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM predictions WHERE actual_outcome IS NULL AND verify_by <= ?",
                (today,)
            ).fetchall()
        return [Prediction(**dict(r)) for r in rows]

    def get_all(self, limit: int = 100) -> List[Prediction]:
        """获取所有预测"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM predictions ORDER BY predicted_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [Prediction(**dict(r)) for r in rows]

    def verify(self, prediction_id: str, outcome: int) -> None:
        """验证单条预测"""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE predictions SET actual_outcome = ?, verified_at = ? WHERE id = ?",
                (outcome, today, prediction_id)
            )

    # ── 校准统计 ──────────────────────────────────────────────

    def calculate_brier_score(self, predictions: List[Prediction] = None) -> float:
        """计算 Brier Score (0=完美, 0.25=随机猜测)"""
        preds = predictions or self.get_verified()
        if not preds:
            return 0.0

        scores = []
        for p in preds:
            if p.actual_outcome is not None:
                scores.append((p.predicted_prob - p.actual_outcome) ** 2)

        return sum(scores) / len(scores) if scores else 0.0

    def calculate_calibration_bias(self, predictions: List[Prediction] = None) -> float:
        """计算校准偏差 (>0 偏乐观, <0 偏悲观)"""
        preds = predictions or self.get_verified()
        if not preds:
            return 0.0

        pred_probs = []
        outcomes = []
        for p in preds:
            if p.actual_outcome is not None:
                pred_probs.append(p.predicted_prob)
                outcomes.append(p.actual_outcome)

        if not pred_probs:
            return 0.0

        return sum(pred_probs) / len(pred_probs) - sum(outcomes) / len(outcomes)

    def get_verified(self) -> List[Prediction]:
        """获取已验证的预测"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM predictions WHERE actual_outcome IS NOT NULL ORDER BY verified_at DESC"
            ).fetchall()
        return [Prediction(**dict(r)) for r in rows]

    def get_stats(self) -> dict:
        """获取校准统计摘要"""
        all_preds = self.get_all(limit=10000)
        verified = [p for p in all_preds if p.actual_outcome is not None]
        total = len(all_preds)
        n_verified = len(verified)
        hit_count = sum(1 for p in verified if p.actual_outcome == 1)

        brier = self.calculate_brier_score(verified)
        bias = self.calculate_calibration_bias(verified)

        # 最近 5 次命中率
        recent_5 = [p for p in verified if p.verified_at][:5]
        recent_hit = sum(1 for p in recent_5 if p.actual_outcome == 1)

        # 评级
        if n_verified < 5:
            rating = "数据不足"
        elif brier < 0.1 and abs(bias) < 0.1:
            rating = "可靠"
        elif bias > 0.2:
            rating = "偏乐观"
        elif bias < -0.2:
            rating = "偏悲观"
        else:
            rating = "待观察"

        return {
            "total_predictions": total,
            "verified_count": n_verified,
            "pending_count": total - n_verified,
            "hit_count": hit_count,
            "hit_rate": f"{hit_count}/{n_verified} ({hit_count/n_verified:.0%})" if n_verified else "N/A",
            "brier_score": round(brier, 4),
            "calibration_bias": round(bias, 4),
            "recent_5_hit_rate": f"{recent_hit}/{min(5, len(recent_5))}",
            "rating": rating,
            "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        }

    def export_scorecard(self) -> dict:
        """导出完整的记分卡数据"""
        all_preds = self.get_all(limit=10000)
        verified = [p for p in all_preds if p.actual_outcome is not None]

        history = []
        for p in all_preds:
            history.append({
                "id": p.id,
                "prediction": p.prediction,
                "predicted_prob": p.predicted_prob,
                "predicted_at": p.predicted_at,
                "verify_by": p.verify_by,
                "actual_outcome": "命中" if p.actual_outcome == 1 else ("未命中" if p.actual_outcome == 0 else "待验证"),
                "agent": p.agent,
                "tags": p.tags
            })

        stats = self.get_stats()
        stats["history"] = history

        # 保存到 scorecard.json
        with open(_SCORECARD_FILE, "w") as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)

        return stats


if __name__ == "__main__":
    # 测试: 创建一些示例预测
    store = PredictionStore()

    # 检查现有统计
    stats = store.get_stats()
    print("=== 预测记分卡 ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    if stats["total_predictions"] == 0:
        print("\n暂无预测记录，运行报告后将自动记录")
