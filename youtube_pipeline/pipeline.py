#!/usr/bin/env python3
"""
MiroFish v3.0 YouTube 自动分析 - 主流水线
扫描 YouTube 频道目录，管理视频处理状态。
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime
from config import (
    ENABLED, YOUTUBE_DIR, REPORTS_DIR, CHECKLIST_PATH,
    CHANNELS, MIROFISH_SPEC_PATH
)


def load_checklist():
    """读取 checklist.json"""
    if Path(CHECKLIST_PATH).exists():
        with open(CHECKLIST_PATH) as f:
            return json.load(f)
    return {"enabled": ENABLED, "videos": {}, "last_scanned": None}


def save_checklist(data):
    """保存 checklist.json"""
    data["last_scanned"] = datetime.now().isoformat()
    with open(CHECKLIST_PATH, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def extract_video_id(filename):
    """从文件名中提取视频 ID (last bracket content before extension)
    例: "H200出售给中国 [GLa6L05-0Rc].mp4" -> "GLa6L05-0Rc"
    """
    stem = Path(filename).stem  # 去掉扩展名
    if "[" in stem and "]" in stem:
        start = stem.rfind("[")
        end = stem.rfind("]")
        if start < end:
            return stem[start+1:end]
    return None


def scan_videos_in_channel(channel_name):
    """扫描频道目录中的视频文件，返回 (video_id, title) 列表"""
    channel_dir = Path(YOUTUBE_DIR) / channel_name
    if not channel_dir.exists():
        print(f"  ⚠️  频道目录不存在: {channel_dir}")
        return []

    videos = []
    transcripts_dir = Path(YOUTUBE_DIR) / "transcripts"

    for mp4_file in sorted(channel_dir.glob("*.mp4")):
        video_id = extract_video_id(mp4_file.name)
        if video_id:
            full_name = mp4_file.stem  # 完整名称包括日期和标题
            # 字幕文件使用新命名约定: "full_name [video_id].txt"
            transcript_file = transcripts_dir / f"{full_name} [{video_id}].txt"
            has_transcript = transcript_file.exists()
            videos.append({
                "video_id": video_id,
                "full_name": full_name,
                "filename": mp4_file.name,
                "has_transcript": has_transcript
            })

    return videos


def scan_all_channels():
    """扫描所有频道，返回 {channel_name: [videos]} 字典"""
    result = {}
    for channel in CHANNELS:
        videos = scan_videos_in_channel(channel)
        result[channel] = videos
    return result


def update_checklist_from_scan(scan_result):
    """根据扫描结果更新 checklist.json"""
    checklist = load_checklist()

    for channel, videos in scan_result.items():
        for video in videos:
            video_id = video["video_id"]

            # 如果视频不在 checklist 中，添加为 pending
            if video_id not in checklist["videos"]:
                checklist["videos"][video_id] = {
                    "video_id": video_id,
                    "full_name": video["full_name"],
                    "channel": channel,
                    "date": video["full_name"].split(" - ")[0] if " - " in video["full_name"] else datetime.now().strftime("%Y%m%d"),
                    "has_transcript": video["has_transcript"],
                    "report_status": "no_transcript" if not video["has_transcript"] else "pending",
                    "report_path": None,
                    "processed_at": None
                }
            else:
                # 更新已有视频的信息
                checklist["videos"][video_id]["full_name"] = video["full_name"]
                checklist["videos"][video_id]["has_transcript"] = video["has_transcript"]

    save_checklist(checklist)
    return checklist


def print_checklist_summary(checklist):
    """打印 checklist 摘要"""
    videos = checklist.get("videos", {})

    status_count = {
        "pending": 0,
        "processing": 0,
        "done": 0,
        "error": 0,
        "no_transcript": 0
    }

    for video in videos.values():
        status = video.get("report_status", "unknown")
        if status in status_count:
            status_count[status] += 1

    print(f"\n📊 Checklist 状态摘要:")
    print(f"   ⏳ 待处理 (pending):      {status_count['pending']:3d}")
    print(f"   🔄 处理中 (processing):  {status_count['processing']:3d}")
    print(f"   ✅ 已完成 (done):        {status_count['done']:3d}")
    print(f"   ❌ 错误 (error):         {status_count['error']:3d}")
    print(f"   🚫 无字幕 (no_transcript): {status_count['no_transcript']:3d}")
    print(f"   总计:                   {len(videos):3d}")


def dry_run():
    """干运行模式：扫描频道，显示统计，不调用 LLM"""
    print("\n" + "="*60)
    print("🔍 Dry-Run 模式：扫描视频 (不调用 LLM)")
    print("="*60)

    if not ENABLED:
        print("⚠️  Pipeline 未启用 (ENABLED=False)")
        print("   设置 config.py 中的 ENABLED=True 以启用自动处理")

    # 扫描所有频道
    print("\n📂 扫描频道...")
    scan_result = scan_all_channels()

    # 统计
    total_videos = sum(len(videos) for videos in scan_result.values())
    total_with_transcript = sum(
        sum(1 for v in videos if v["has_transcript"])
        for videos in scan_result.values()
    )

    print(f"\n📺 扫描结果:")
    for channel, videos in scan_result.items():
        with_transcript = sum(1 for v in videos if v["has_transcript"])
        print(f"   {channel}: {len(videos)} 个视频 ({with_transcript} 有字幕)")

    print(f"\n📊 总计: {total_videos} 个视频, {total_with_transcript} 个有字幕")

    # 更新 checklist
    print(f"\n💾 更新 checklist.json...")
    checklist = update_checklist_from_scan(scan_result)
    print_checklist_summary(checklist)

    print("\n" + "="*60)
    print("✅ 干运行完成")
    print("="*60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="MiroFish v3.0 YouTube 自动分析流水线"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="干运行模式：扫描视频但不调用 LLM"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="详细输出模式"
    )

    args = parser.parse_args()

    if args.dry_run:
        dry_run()
    else:
        print("Usage: python pipeline.py --dry-run")
        print("\nOptions:")
        print("  --dry-run    Scan and show summary without calling LLM")
        print("  --verbose    Show detailed output")


if __name__ == "__main__":
    main()
