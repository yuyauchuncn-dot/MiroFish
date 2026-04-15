#!/usr/bin/env python3
"""
MiroFish 流水线：第 3 步 - 生成 MiroFish 报告
接受：<video_id> 或从 /tmp/mirofish_step.env 读取
调用 report_generator.py --test 生成报告
"""

import re
import sys
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

# Import path configuration from config module
_script_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(_script_dir))
from config import REPORTS_DIR
sys.path.pop(0)

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


def save_step_env(env):
    """保存步骤环境文件"""
    with open(STEP_ENV, 'w', encoding='utf-8') as f:
        for k, v in env.items():
            f.write(f"{k}={v}\n")


def find_existing_report(channel, video_id, use_v4=False):
    """查找已存在的报告文件

    Args:
        channel: 频道名称
        video_id: 视频 ID
        use_v4: True = 查找 _v4_MiroFish.md, False = 查找 _MiroFish.md（非 v4）
    """
    channel_dir = REPORTS_DIR / channel
    if not channel_dir.exists():
        return None

    suffix = "_v4_MiroFish.md" if use_v4 else "_MiroFish.md"
    for report_file in channel_dir.glob(f"*{video_id}*{suffix}"):
        return report_file

    return None


def main():
    print("\n" + "="*70)
    print("🔍 第 3 步：生成 MiroFish 报告")
    print("="*70 + "\n")

    # 读取环境文件
    env = load_step_env()
    video_id = env.get('VIDEO_ID')
    channel = env.get('CHANNEL')
    use_v4 = env.get('USE_V4', 'true').lower() == 'true'

    # 检查 --v4 标志
    if '--v4' in sys.argv:
        use_v4 = True

    # Check if we have pre-fetched transcript text from monofetchers
    env = load_step_env()
    transcript_text = env.get('TRANSCRIPT_TEXT', '')

    # 命令行参数优先（可能是 video_id 或 YouTube URL）
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        # 如果是 URL，提取 video_id
        if arg.startswith('http'):
            import re
            m = re.search(r'v=([a-zA-Z0-9_-]+)', arg) or re.search(r'youtu\.be/([a-zA-Z0-9_-]+)', arg)
            if m:
                video_id = m.group(1)
            else:
                print(f"⚠️  无法从 URL 提取 video_id，使用环境变量")
        else:
            video_id = arg

    if not video_id:
        print("❌ 无法获取 VIDEO_ID")
        sys.exit(1)

    print(f"🎯 Video ID：{video_id}")
    print(f"📦 框架：{'v4 (多代理辩论 + 预测引擎)' if use_v4 else 'v3'}")

    # 检查是否已生成过报告
    if channel:
        existing_report = find_existing_report(channel, video_id, use_v4=use_v4)
        if existing_report and existing_report.exists():
            print(f"\n✓ 报告已存在：{existing_report.name}")
            file_size = existing_report.stat().st_size
            print(f"  📄 文件大小：{file_size} 字节")
            print("✅ 报告生成完成（使用现有文件）")
            return

    # 确保 checklist 包含当前视频（幂等操作，安全重复运行）
    script_dir = Path(__file__).parent
    rebuild_checklist = script_dir / "rebuild_checklist.py"
    if rebuild_checklist.exists():
        print(f"\n🔄 更新 checklist（确保视频已注册）...")
        rebuild_result = subprocess.run(
            ["python3", str(rebuild_checklist)],
            cwd=str(script_dir),
            capture_output=True,
            text=True
        )
        if rebuild_result.returncode != 0:
            print(f"⚠️  checklist 更新失败（将继续尝试生成报告）: {rebuild_result.stderr[:200]}")
        else:
            print(f"✓ checklist 已更新")

    # 调用 report_generator.py --test <video_id>
    report_generator = script_dir / "report_generator.py"

    if not report_generator.exists():
        print(f"❌ report_generator.py 不存在：{report_generator}")
        sys.exit(1)

    print(f"\n📝 调用报告生成器...")
    cmd = ["python3", str(report_generator), "--test", video_id]
    if use_v4:
        cmd.append("--v4")

    # Pass transcript_text via temp file (avoids shell quoting for large strings)
    transcript_file = None
    if transcript_text:
        transcript_file = Path(tempfile.mktemp(suffix="_transcript.txt"))
        transcript_file.write_text(transcript_text, encoding="utf-8")
        cmd.extend(["--transcript-text-file", str(transcript_file)])

    try:
        result = subprocess.run(cmd, cwd=str(script_dir))
    finally:
        if transcript_file and transcript_file.exists():
            transcript_file.unlink()

    if result.returncode != 0:
        print(f"\n❌ 报告生成失败")
        sys.exit(1)

    print(f"\n✅ 报告生成完成（新生成）")


if __name__ == "__main__":
    main()
