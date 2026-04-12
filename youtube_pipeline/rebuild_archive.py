#!/usr/bin/env python3
"""
重建 download_archive.txt：
1. 扫描所有频道目录下的 mp4 文件
2. 提取视频 ID（[VIDEO_ID] 格式）
3. 生成标准 archive 格式，每行一个 ID：youtube {video_id}
4. 原子替换写回 download_archive.txt

生成扩展信息文件 download_archive_extended.json，记录每个 video_id 的详细信息。
"""

import json
import re
import signal
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

# Import path configuration from config module
_script_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(_script_dir))
from config import YOUTUBE_DIR
sys.path.pop(0)

_YT = Path(YOUTUBE_DIR)
ARCHIVE_FILE = _YT / "download_archive.txt"
ARCHIVE_EXTENDED_FILE = _YT / "download_archive_extended.json"
TEMP_ARCHIVE_FILE = _YT / "download_archive.txt.tmp"
IGNORED_DIR = _YT / "ignored"


def _signal_handler(signum, frame):
    """处理 Ctrl+C / SIGINT 信号"""
    print("\n")
    print("📌 操作已中断，已保存进度")
    sys.exit(130)


# 注册信号处理器
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def extract_video_id_from_filename(filename):
    """从文件名中提取 [VIDEO_ID]，格式: ... [VIDEO_ID].mp4"""
    match = re.search(r'\[([^\]]+)\]\.mp4$', filename)
    if match:
        return match.group(1)
    return None


def guess_channel_from_path(file_path):
    """从文件路径推断频道名（使用第一级子目录）"""
    try:
        relative = file_path.relative_to(_YT)
        parts = relative.parts
        if len(parts) > 1:
            # 文件在子目录中，返回子目录名
            return parts[0]
        else:
            # 文件在根目录中
            return "Unknown"
    except ValueError:
        return "Unknown"


def rebuild_archive():
    """重建 archive 文件"""
    print("\n" + "=" * 70)
    print("🔄 重建 download_archive.txt...")
    print("=" * 70)

    # 扫描所有 mp4 文件
    print("\n🔍 扫描 MP4 文件...")
    video_mapping = {}
    channel_count = defaultdict(int)

    for mp4_file in _YT.rglob("*.mp4"):
        if not mp4_file.is_file():
            continue

        # Skip videos in the ignored directory
        if IGNORED_DIR in mp4_file.parents:
            continue

        filename = mp4_file.name
        video_id = extract_video_id_from_filename(filename)

        if not video_id:
            print(f"⚠️  无法提取 video_id: {filename[:60]}...")
            continue

        # 推断频道
        channel = guess_channel_from_path(mp4_file)

        # 提取日期（格式：YYYYMMDD - ...）
        date_match = re.match(r'^(\d{8})', filename)
        date_str = date_match.group(1) if date_match else datetime.now().strftime("%Y%m%d")

        video_mapping[video_id] = {
            "filename": filename,
            "channel": channel,
            "date": date_str,
            "file_path": str(mp4_file)
        }

        channel_count[channel] += 1

    total_videos = len(video_mapping)
    print(f"✓ 扫描完成：找到 {total_videos} 个唯一视频")

    # 打印频道统计
    print("\n📊 频道分布:")
    for channel, count in sorted(channel_count.items(), key=lambda x: -x[1]):
        print(f"   • {channel}: {count}")

    # 生成 archive 文件（标准格式）
    print("\n📝 生成 archive 文件...")

    archive_lines = []
    for video_id in sorted(video_mapping.keys()):
        archive_lines.append(f"youtube {video_id}")

    # 原子写入：先写临时文件，再重命名
    try:
        with open(TEMP_ARCHIVE_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(archive_lines))

        # 备份旧文件
        if ARCHIVE_FILE.exists():
            backup_file = ARCHIVE_FILE.with_suffix(".txt.bak")
            ARCHIVE_FILE.rename(backup_file)
            print(f"✓ 旧 archive 已备份至: {backup_file.name}")

        # 原子重命名
        TEMP_ARCHIVE_FILE.rename(ARCHIVE_FILE)
        print(f"✓ 新 archive 已保存: {ARCHIVE_FILE.name} ({total_videos} 行)")

    except Exception as e:
        print(f"❌ 写入失败: {e}")
        if TEMP_ARCHIVE_FILE.exists():
            TEMP_ARCHIVE_FILE.unlink()
        return False

    # 生成扩展信息文件（JSON）
    print("\n📋 生成扩展信息文件...")
    try:
        with open(ARCHIVE_EXTENDED_FILE, "w", encoding="utf-8") as f:
            json.dump(video_mapping, f, ensure_ascii=False, indent=2)
        print(f"✓ 扩展信息已保存: {ARCHIVE_EXTENDED_FILE.name}")
    except Exception as e:
        print(f"⚠️  扩展信息保存失败: {e}")

    # 汇总
    print("\n" + "=" * 70)
    print("✅ Archive 重建完成")
    print("=" * 70)
    print(f"   • 总视频数: {total_videos}")
    print(f"   • Archive 文件: {ARCHIVE_FILE}")
    print(f"   • 扩展信息: {ARCHIVE_EXTENDED_FILE}")
    print("=" * 70 + "\n")

    return True


def main():
    rebuild_archive()


if __name__ == "__main__":
    main()
