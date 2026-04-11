#!/usr/bin/env python3
"""Convert WebVTT files to plain text transcripts."""
import os
import re
import sys

def convert_vtt_to_txt(vtt_path, txt_path):
    """Convert VTT file to TXT by removing timestamps and formatting."""
    print(f"Converting {os.path.basename(vtt_path)} → {os.path.basename(txt_path)}")

    try:
        with open(vtt_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"  ✗ Error reading {vtt_path}: {e}")
        return False

    output_lines = []
    for line in lines:
        line = line.rstrip('\n')

        # Skip header
        if line.startswith('WEBVTT'):
            continue

        # Skip blank lines and timestamp lines
        if not line or '-->' in line:
            continue

        # Skip pure numeric lines (cue numbers)
        if line.isdigit():
            continue

        # Remove inline timestamps like <00:12:34>
        line = re.sub(r'<\d{2}:\d{2}:\d{2}>', '', line).strip()

        # Only add non-empty lines
        if line:
            output_lines.append(line)

    try:
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(output_lines))
        print(f"  ✓ Saved {os.path.basename(txt_path)}")
        return True
    except Exception as e:
        print(f"  ✗ Error writing {txt_path}: {e}")
        return False

def process_channel(channel_dir):
    """Process all VTT files in a channel directory."""
    if not os.path.isdir(channel_dir):
        print(f"Directory not found: {channel_dir}")
        return 0

    converted = 0
    for filename in sorted(os.listdir(channel_dir)):
        if filename.endswith('.vtt'):
            vtt_path = os.path.join(channel_dir, filename)
            txt_path = vtt_path[:-4] + '.txt'

            # Skip if .txt already exists
            if os.path.exists(txt_path):
                print(f"Skipping {os.path.basename(vtt_path)} (txt exists)")
                continue

            if convert_vtt_to_txt(vtt_path, txt_path):
                converted += 1

    return converted

if __name__ == '__main__':
    base_dir = "Path(__file__).resolve().parent.parent.parent.parent / 'data' / 'raw' / 'media' / 'youtube_downloads'"
    channels = ["Henry 的慢思考", "老厉害"]

    if len(sys.argv) > 1:
        # Process specific channel
        channels = [sys.argv[1]]

    total_converted = 0
    for channel in channels:
        channel_path = os.path.join(base_dir, channel)
        print(f"\n📂 Processing {channel}...")
        count = process_channel(channel_path)
        total_converted += count
        print(f"  → {count} files converted")

    print(f"\n✓ Total: {total_converted} VTT→TXT conversions completed")
