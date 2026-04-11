#!/usr/bin/env python3
"""
整理 transcripts/ 目录：
1. 扫描 transcripts/ 中的所有文件
2. 提取 video_id，查找对应频道目录中的 mp4 文件
3. 重复处理策略：
   - 若频道目录中已有同 ID 的 transcript → 删除 transcripts/ 中的旧文件
   - 若频道目录中没有 → 移动到对应频道目录
4. 无 mp4 匹配的 → 保留在 transcripts/，打印警告
5. 打印操作摘要（移动数、删除数、保留数）
"""

import json
import re
import signal
import sys
from pathlib import Path
from datetime import datetime

YOUTUBE_DIR = Path("Path(__file__).resolve().parent.parent.parent.parent / 'data' / 'raw' / 'media' / 'youtube_downloads'")
TRANSCRIPTS_DIR = YOUTUBE_DIR / "transcripts"
ARCHIVE_EXTENDED_FILE = YOUTUBE_DIR / "download_archive_extended.json"


def _signal_handler(signum, frame):
    """处理 Ctrl+C / SIGINT 信号"""
    print("\n")
    print("📌 操作已中断，已保存进度")
    sys.exit(130)


# 注册信号处理器
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def extract_video_id_from_filename(filename):
    """从文件名中提取 [VIDEO_ID]，支持 .txt, .vtt, .srt 格式"""
    match = re.search(r'\[([^\]]+)\]\.(txt|vtt|srt)$', filename)
    if match:
        return match.group(1)
    return None


def load_video_mapping():
    """从 archive_extended.json 加载 video_id -> channel 映射"""
    mapping = {}
    if ARCHIVE_EXTENDED_FILE.exists():
        with open(ARCHIVE_EXTENDED_FILE, encoding="utf-8") as f:
            data = json.load(f)
            for video_id, info in data.items():
                mapping[video_id] = info.get("channel", "Unknown")
    return mapping


def check_transcript_in_channel(video_id, channel):
    """检查频道目录中是否已有该 video_id 的 transcript"""
    if channel == "Unknown":
        return False

    channel_dir = YOUTUBE_DIR / channel
    if not channel_dir.exists():
        return False

    # 查找该频道目录中是否有相同 video_id 的 transcript
    for ext in ["txt", "vtt", "srt"]:
        # 支持两种格式：full_name [VIDEO_ID].ext 或 [VIDEO_ID].ext
        pattern1 = f"* [{video_id}].{ext}"
        pattern2 = f"[{video_id}].{ext}"

        matches1 = list(channel_dir.glob(pattern1))
        matches2 = list(channel_dir.glob(pattern2))

        if matches1 or matches2:
            return True

    return False


def migrate_transcripts():
    """整理 transcripts 目录"""
    print("\n" + "=" * 70)
    print("🔄 整理 transcripts/ 目录...")
    print("=" * 70)

    if not TRANSCRIPTS_DIR.exists():
        print("❌ transcripts 目录不存在")
        return False

    # 加载 video_id -> channel 映射
    print("\n📋 加载 archive 映射信息...")
    video_mapping = load_video_mapping()
    print(f"✓ 加载 {len(video_mapping)} 个视频映射")

    # 扫描 transcripts 目录
    print("\n🔍 扫描 transcripts/ 目录...")
    transcript_files = list(TRANSCRIPTS_DIR.glob("*.[tvs]*"))  # .txt, .vtt, .srt
    print(f"✓ 找到 {len(transcript_files)} 个文件")

    moved_count = 0
    deleted_count = 0
    preserved_count = 0
    no_mp4_match = []

    print("\n📊 处理文件...")
    for transcript_file in transcript_files:
        filename = transcript_file.name
        video_id = extract_video_id_from_filename(filename)

        if not video_id:
            print(f"⚠️  无法提取 video_id: {filename[:50]}...")
            continue

        # 查找该 video_id 对应的频道
        channel = video_mapping.get(video_id)

        if not channel or channel == "Unknown":
            # 没有对应的 mp4 文件
            print(f"🔵 [保留] {filename[:50]}... (无 mp4 匹配)")
            no_mp4_match.append(filename)
            preserved_count += 1
            continue

        # 检查频道目录中是否已有
        if check_transcript_in_channel(video_id, channel):
            # 频道目录已有，删除 transcripts/ 中的
            try:
                transcript_file.unlink()
                print(f"🗑️  [删除] {filename[:50]}... (频道目录已有)")
                deleted_count += 1
            except Exception as e:
                print(f"❌ [失败] 删除 {filename[:50]}...: {e}")
        else:
            # 频道目录没有，移动过去
            channel_dir = YOUTUBE_DIR / channel
            channel_dir.mkdir(parents=True, exist_ok=True)

            try:
                new_path = channel_dir / filename
                transcript_file.rename(new_path)
                print(f"✅ [移动] {filename[:50]}... → {channel}")
                moved_count += 1
            except Exception as e:
                print(f"❌ [失败] 移动 {filename[:50]}...: {e}")

    # 汇总
    print("\n" + "=" * 70)
    print("✅ Transcripts 整理完成")
    print("=" * 70)
    print(f"   • 移动: {moved_count}")
    print(f"   • 删除: {deleted_count}")
    print(f"   • 保留: {preserved_count}")
    print(f"   • 总处理: {moved_count + deleted_count + preserved_count}")

    if no_mp4_match:
        print(f"\n⚠️  以下文件无 mp4 匹配，已保留在 transcripts/:")
        for f in no_mp4_match:
            print(f"   • {f}")

    print("=" * 70 + "\n")

    return True


def main():
    migrate_transcripts()


if __name__ == "__main__":
    main()
