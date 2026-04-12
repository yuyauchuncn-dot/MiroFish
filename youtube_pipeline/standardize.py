#!/usr/bin/env python3
"""
Standardize video names across the pipeline:
- Rename transcript files to use full video names
- Update report naming conventions
- Rebuild checklist with new naming scheme
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

# Import path configuration from config module
_script_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(_script_dir))
from config import YOUTUBE_DIR, TRANSCRIPTS_DIR, REPORTS_DIR, CHANNELS
sys.path.pop(0)

def build_video_mapping():
    """Build mapping of video_id -> (full_name, channel, file_path)"""
    mapping = {}

    for channel in CHANNELS:
        channel_dir = YOUTUBE_DIR / channel
        if not channel_dir.exists():
            continue

        for file_path in channel_dir.glob("*.mp4"):
            filename = file_path.stem  # Remove .mp4 extension
            # Extract video ID from format: "date - title [VIDEO_ID]"
            match = re.search(r'\[([^\]]+)\]$', filename)
            if match:
                video_id = match.group(1)
                mapping[video_id] = {
                    'full_name': filename,
                    'channel': channel,
                    'file_path': str(file_path)
                }

    return mapping

def rename_transcripts(mapping):
    """Rename transcript files from video_id.txt to full_name [VIDEO_ID].txt"""
    if not TRANSCRIPTS_DIR.exists():
        print("⚠️ Transcripts directory not found")
        return

    renamed_count = 0
    for old_file in TRANSCRIPTS_DIR.glob("*.txt"):
        video_id = old_file.stem

        if video_id not in mapping:
            print(f"⚠️ Skipping {old_file.name}: No video mapping found")
            continue

        # New name: {full_name} [{video_id}].txt
        new_name = f"{mapping[video_id]['full_name']} [{video_id}].txt"
        new_file = TRANSCRIPTS_DIR / new_name

        if new_file.exists():
            print(f"⚠️ Already exists: {new_name}")
            continue

        try:
            old_file.rename(new_file)
            print(f"✓ Renamed: {old_file.name} → {new_name}")
            renamed_count += 1
        except Exception as e:
            print(f"✗ Error renaming {old_file.name}: {e}")

    print(f"\n📝 Total renamed: {renamed_count}")

def update_reports(mapping):
    """Update report names to use full video names"""
    updated_count = 0

    for channel in CHANNELS:
        channel_report_dir = REPORTS_DIR / channel
        if not channel_report_dir.exists():
            continue

        for old_file in channel_report_dir.glob("*_MiroFish.md"):
            # Extract video_id from current name: "20260329_PdJEZcRV-UY_MiroFish.md"
            match = re.search(r'_([a-zA-Z0-9_-]+)_MiroFish\.md$', old_file.name)
            if not match:
                continue

            video_id = match.group(1)
            if video_id not in mapping:
                print(f"⚠️ Skipping {old_file.name}: No video mapping found")
                continue

            # New name: {date}_{full_name} [{video_id}]_MiroFish.md
            date = datetime.now().strftime("%Y%m%d")
            full_name = mapping[video_id]['full_name']
            new_name = f"{date}_{full_name} [{video_id}]_MiroFish.md"
            new_file = channel_report_dir / new_name

            if new_file.exists():
                print(f"⚠️ Already exists: {new_name}")
                continue

            try:
                old_file.rename(new_file)
                print(f"✓ Renamed report: {old_file.name} → {new_name}")
                updated_count += 1
            except Exception as e:
                print(f"✗ Error renaming {old_file.name}: {e}")

    print(f"\n📝 Total reports updated: {updated_count}")

def print_mapping_summary(mapping):
    """Print summary of video mapping"""
    print("\n" + "="*70)
    print("VIDEO MAPPING SUMMARY")
    print("="*70)

    by_channel = {}
    for video_id, info in mapping.items():
        channel = info['channel']
        if channel not in by_channel:
            by_channel[channel] = []
        by_channel[channel].append(video_id)

    for channel in CHANNELS:
        count = len(by_channel.get(channel, []))
        print(f"\n{channel}: {count} videos")
        for video_id in sorted(by_channel.get(channel, []))[:5]:
            print(f"  • {video_id}: {mapping[video_id]['full_name'][:60]}...")
        if len(by_channel.get(channel, [])) > 5:
            print(f"  ... and {len(by_channel.get(channel, [])) - 5} more")

if __name__ == "__main__":
    print("\n🔄 Building video ID mapping...")
    mapping = build_video_mapping()
    print(f"✓ Found {len(mapping)} videos")

    print("\n" + "="*70)
    print("STEP 1: RENAME TRANSCRIPT FILES")
    print("="*70)
    rename_transcripts(mapping)

    print("\n" + "="*70)
    print("STEP 2: UPDATE REPORT NAMES")
    print("="*70)
    update_reports(mapping)

    print_mapping_summary(mapping)
    print("\n✅ Standardization complete!")
