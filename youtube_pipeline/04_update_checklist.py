#!/usr/bin/env python3
"""
MiroFish 流水线：第 4 步 - 更新清单
接受：无（或 <video_id>）
调用 rebuild_checklist.py 更新 checklist.json
"""

import os
import sys
import subprocess
from pathlib import Path

STEP_ENV = "/tmp/mirofish_step.env"


def load_step_env():
    """读取步骤环境文件"""
    env = {}
    if Path(STEP_ENV).exists():
        with open(STEP_ENV, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    k, v = line.split('=', 1)
                    env[k] = v
    return env


def main():
    print("\n" + "="*70)
    print("📋 第 4 步：更新清单")
    print("="*70 + "\n")

    # 读取环境文件
    env = load_step_env()
    video_id = env.get('VIDEO_ID')

    if video_id:
        print(f"🎯 Video ID：{video_id}")

    # 调用 rebuild_checklist.py
    script_dir = Path(__file__).parent
    rebuild_checklist = script_dir / "rebuild_checklist.py"

    if not rebuild_checklist.exists():
        print(f"❌ rebuild_checklist.py 不存在：{rebuild_checklist}")
        sys.exit(1)

    print(f"\n🔄 重建 checklist.json...")
    result = subprocess.run(
        ["python3", str(rebuild_checklist)],
        cwd=str(script_dir)
    )

    if result.returncode != 0:
        print(f"\n❌ 清单更新失败")
        sys.exit(1)

    print(f"\n✅ 清单更新完成")


if __name__ == "__main__":
    main()
