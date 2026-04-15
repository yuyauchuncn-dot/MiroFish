#!/usr/bin/env python3
"""
Rebuild checklist.json with intelligent merging:
1. Preserve completed videos (report_path exists)
2. Update has_transcript based on actual transcript files
3. Add new videos not yet in checklist
4. Fix duplicated video_id in transcript filenames
按 Ctrl+C (ESC) 可安全中断
"""

import json
import re
import signal
import sys
import shutil
from pathlib import Path
from datetime import datetime

# Import path configuration from config module
_script_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(_script_dir))
from config import YOUTUBE_DIR, TRANSCRIPTS_DIR, REPORTS_DIR
sys.path.pop(0)

# Convert to Path objects
_YT = Path(YOUTUBE_DIR)
_TS = Path(TRANSCRIPTS_DIR)
_RS = Path(REPORTS_DIR)

# Additional local paths
IGNORED_DIR = _YT / "ignored"
CHECKLIST_FILE = Path(__file__).parent / "checklist.json"


def _signal_handler(signum, frame):
    """处理 Ctrl+C / SIGINT 信号"""
    print("\n")
    print("📌 操作已中断，已保存进度")
    sys.exit(130)


# 注册信号处理器
signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)


def clear_ytdlp_cache():
    """清理 yt-dlp 缓存"""
    cache_paths = [
        Path.home() / ".cache" / "yt-dlp",
        Path.home() / "Library" / "Caches" / "yt-dlp",
    ]

    for cache_path in cache_paths:
        if cache_path.exists():
            try:
                shutil.rmtree(cache_path)
                print(f"✓ 清理缓存: {cache_path}")
            except Exception as e:
                print(f"⚠️  清理缓存失败 {cache_path}: {e}")


def fix_transcript_names():
    """Fix transcript files with duplicated video_id pattern"""
    print("\n" + "="*70)
    print("🔧 Fixing transcript file names...")
    print("="*70)

    if not _TS.exists():
        print("Transcripts directory does not exist")
        return 0

    renamed_count = 0
    # Recursively search all transcript files (may be in channel subdirectories)
    for f in _TS.rglob('*.txt'):
        name = f.name
        # Match pattern: ... [VIDEO_ID] [VIDEO_ID].txt (duplicated)
        match = re.search(r'^(.*)\[([^\]]+)\] \[\2\]\.txt$', name)
        if match:
            base_name = match.group(1).rstrip()
            video_id = match.group(2)
            # New name: ensure there's a space before [VIDEO_ID]
            # base_name might end with space or not, we want exactly one space
            base_name = base_name.rstrip()
            new_name = f"{base_name} [{video_id}].txt"
            new_path = f.parent / new_name

            # Check if target file already exists
            if new_path.exists():
                print(f"⚠️  Target already exists: {new_name}")
                print(f"   Skipping: {f.name}")
            else:
                f.rename(new_path)
                renamed_count += 1
                print(f"✅ Renamed: {f.name[:80]}... → {new_name[:80]}...")

    print("\n" + "="*70)
    print(f"Renamed {renamed_count} transcript files")
    print("="*70 + "\n")
    return renamed_count


def guess_channel_from_path(file_path: Path, youtube_dir: Path) -> str:
    """Guess channel name from file path"""
    try:
        relative = file_path.relative_to(youtube_dir)
        parts = relative.parts
        if len(parts) > 1:
            # File is in a subdirectory, use first subdirectory as channel
            return parts[0]
        else:
            # File is in root directory
            return "Unknown"
    except ValueError:
        return "Unknown"


def build_video_mapping():
    """Build mapping of video_id -> (full_name, channel, date)"""
    mapping = {}

    # Recursively search all .mp4 files under YOUTUBE_DIR
    for file_path in _YT.rglob("*.mp4"):
        if not file_path.is_file():
            continue

        # Skip videos in the ignored directory
        if IGNORED_DIR in file_path.parents:
            continue

        filename = file_path.stem
        # Extract video ID from format: "date - title [VIDEO_ID]"
        match = re.search(r'\[([^\]]+)\]$', filename)
        if match:
            video_id = match.group(1)
            # Extract date from start of filename (format: YYYYMMDD)
            date_match = re.match(r'^(\d{8})', filename)
            date = date_match.group(1) if date_match else datetime.now().strftime("%Y%m%d")

            # Guess channel from directory structure
            channel = guess_channel_from_path(file_path, _YT)

            mapping[video_id] = {
                'full_name': filename,
                'channel': channel,
                'date': date,
                'file_path': str(file_path)
            }

    return mapping


def check_transcript_exists(video_id, full_name, channel=None):
    """Check if transcript exists (standard naming: full_name [video_id].txt or .vtt or .srt)

    Check in multiple locations:
    1. Channel directory (same as video file)
    2. Central transcripts directory
    3. YOUTUBE_DIR root
    Support .txt, .vtt, and .srt formats
    """
    exists, path = find_transcript(video_id, full_name, channel)
    return exists


def find_transcript(video_id, full_name, channel=None):
    """Find transcript file and return (exists, path) tuple.

    Search order:
    1. Channel directory under YOUTUBE_DIR (same as video file)
    2. Central transcripts directory under YOUTUBE_DIR (legacy)
    3. monodata/raw/youtube/ channel subdirectory (new)
    4. monodata/raw/youtube/ root
    5. YOUTUBE_DIR root

    Returns:
        tuple: (bool, str or None) - (exists, absolute_path)
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

    def _check_formats(search_dir):
        """Check for .txt, .vtt, .srt in a directory."""
        for name in [transcript_name, vtt_name, srt_name]:
            f = search_dir / name
            if f.exists():
                return True, str(f)
        return False, None

    # 1. Channel directory under YOUTUBE_DIR
    if channel and channel != "Unknown":
        found, path = _check_formats(_YT / channel)
        if found:
            return True, path

    # 2. Central transcripts directory under YOUTUBE_DIR (legacy)
    found, path = _check_formats(_YT / "transcripts")
    if found:
        return True, path

    # 3. monodata/raw/youtube/ channel subdirectory (new location)
    if channel and channel != "Unknown":
        found, path = _check_formats(_TS / channel)
        if found:
            return True, path

    # 4. monodata/raw/youtube/ root
    found, path = _check_formats(_TS)
    if found:
        return True, path

    # 5. YOUTUBE_DIR root
    found, path = _check_formats(_YT)
    if found:
        return True, path

    return False, None


def check_report_exists(video_id, full_name, channel):
    """Check if report file already exists for this video.

    Matches filenames in the format: {date}_{video_id}_{short_title}_MiroFish.md
    or {date}_{video_id}_{short_title}_v4_MiroFish.md
    """
    if not _RS.exists():
        return False, None

    channel_report_dir = _RS / channel
    if not channel_report_dir.exists():
        return False, None

    for report_file in channel_report_dir.glob("*_MiroFish*.md"):
        # Match by _{video_id}_ in filename (works with both old and new formats)
        if f"_{video_id}_" in report_file.name or f"[{video_id}]" in report_file.name:
            return True, str(report_file)

    return False, None


def merge_with_existing(new_mapping, existing_checklist):
    """
    Merge new video mapping with existing checklist:
    - Preserve completed videos (report_status="done" with valid report_path)
    - Update has_transcript based on actual files
    - Add new videos
    """
    merged = {
        "enabled": existing_checklist.get("enabled", False),
        "videos": {},
        "last_scanned": datetime.now().isoformat()
    }

    preserved_count = 0
    updated_count = 0
    added_count = 0
    no_transcript_count = 0

    # Process all videos from mapping
    for video_id, info in new_mapping.items():
        full_name = info['full_name']
        channel = info['channel']
        date = info['date']

        # Check if video exists in existing checklist
        existing_video = existing_checklist.get("videos", {}).get(video_id)

        # Check actual transcript existence (check channel dir + transcripts dir)
        has_transcript, transcript_path = find_transcript(video_id, full_name, channel)

        # Check if report already exists
        report_exists, report_path = check_report_exists(video_id, full_name, channel)

        if existing_video:
            # Video exists in checklist - preserve or update
            existing_status = existing_video.get("report_status")
            existing_report_path = existing_video.get("report_path")

            # If marked as done and report file exists, preserve status
            if existing_status == "done" and existing_report_path:
                report_file = Path(existing_report_path)
                if report_file.exists():
                    # Preserve completed status
                    merged["videos"][video_id] = {
                        "video_id": video_id,
                        "full_name": full_name,
                        "channel": channel,
                        "date": date,
                        "has_transcript": True,  # Completed videos must have had transcript
                        "transcript_path": transcript_path,
                        "report_status": "done",
                        "report_path": existing_report_path,
                        "processed_at": existing_video.get("processed_at")
                    }
                    preserved_count += 1
                    continue

            # Report doesn't exist or status not done - update based on actual files
            if report_exists and report_path:
                # Report found - mark as done
                report_status = "done"
                merged["videos"][video_id] = {
                    "video_id": video_id,
                    "full_name": full_name,
                    "channel": channel,
                    "date": date,
                    "has_transcript": True,  # Must have transcript if report exists
                    "transcript_path": transcript_path,
                    "report_status": report_status,
                    "report_path": report_path,
                    "processed_at": existing_video.get("processed_at") if existing_video else None
                }
                preserved_count += 1  # Count as preserved completion
            elif has_transcript:
                # Has transcript but no report - pending
                report_status = "pending"
                merged["videos"][video_id] = {
                    "video_id": video_id,
                    "full_name": full_name,
                    "channel": channel,
                    "date": date,
                    "has_transcript": has_transcript,
                    "transcript_path": transcript_path,
                    "report_status": report_status,
                    "report_path": None,
                    "processed_at": None
                }
                updated_count += 1
            else:
                # No transcript, no report
                report_status = "no_transcript"
                no_transcript_count += 1
                merged["videos"][video_id] = {
                    "video_id": video_id,
                    "full_name": full_name,
                    "channel": channel,
                    "date": date,
                    "has_transcript": has_transcript,
                    "transcript_path": None,
                    "report_status": report_status,
                    "report_path": None,
                    "processed_at": None
                }
                updated_count += 1
        else:
            # New video not in checklist - add it
            if report_exists and report_path:
                # Report already exists for new video
                report_status = "done"
                merged["videos"][video_id] = {
                    "video_id": video_id,
                    "full_name": full_name,
                    "channel": channel,
                    "date": date,
                    "has_transcript": True,
                    "transcript_path": transcript_path,
                    "report_status": report_status,
                    "report_path": report_path,
                    "processed_at": None
                }
                added_count += 1
            elif has_transcript:
                # Has transcript but no report
                report_status = "pending"
                merged["videos"][video_id] = {
                    "video_id": video_id,
                    "full_name": full_name,
                    "channel": channel,
                    "date": date,
                    "has_transcript": has_transcript,
                    "transcript_path": transcript_path,
                    "report_status": report_status,
                    "report_path": None,
                    "processed_at": None
                }
                added_count += 1
            else:
                # No transcript, no report
                report_status = "no_transcript"
                no_transcript_count += 1
                merged["videos"][video_id] = {
                    "video_id": video_id,
                    "full_name": full_name,
                    "channel": channel,
                    "date": date,
                    "has_transcript": has_transcript,
                    "transcript_path": None,
                    "report_status": report_status,
                    "report_path": None,
                    "processed_at": None
                }
                added_count += 1

    return merged, preserved_count, updated_count, added_count, no_transcript_count


def rebuild_checklist():
    """Main function to rebuild checklist.json"""
    print("\n" + "="*70)
    print("🔄 Rebuilding checklist.json...")
    print("="*70)

    # Load existing checklist if exists
    existing_checklist = {}
    if CHECKLIST_FILE.exists():
        with open(CHECKLIST_FILE, encoding="utf-8") as f:
            existing_checklist = json.load(f)
        print(f"📄 Loaded existing checklist: {len(existing_checklist.get('videos', {}))} videos")
    else:
        print("📄 No existing checklist found, creating new one")

    # Build video mapping from actual files
    print("\n🔍 Scanning video files...")
    mapping = build_video_mapping()
    print(f"✓ Found {len(mapping)} videos on disk")

    # Merge with existing
    print("\n🔗 Merging with existing checklist...")
    merged, preserved, updated, added, no_transcript = merge_with_existing(mapping, existing_checklist)

    # Count pending (have transcript, not done)
    pending = sum(1 for v in merged["videos"].values()
                  if v["report_status"] == "pending")

    # Save to file
    with open(CHECKLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print("\n" + "="*70)
    print("✅ Checklist rebuilt successfully:")
    print("="*70)
    print(f"   • Total videos: {len(merged['videos'])}")
    print(f"   • 🟢 Preserved (done): {preserved}")
    print(f"   • 🔄 Updated/refreshed: {updated}")
    print(f"   • ➕ New videos added: {added}")
    print(f"   • ⏳ Pending (have transcript): {pending}")
    print(f"   • 📄 No transcript: {no_transcript}")
    print(f"   • 💾 Saved to: {CHECKLIST_FILE}")
    print("="*70 + "\n")


def main():
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--fix-names':
        # Just fix transcript names without rebuilding checklist
        fix_transcript_names()
        rebuild_checklist()
    else:
        # Fix names first, then rebuild checklist
        fix_transcript_names()
        rebuild_checklist()


if __name__ == "__main__":
    main()
