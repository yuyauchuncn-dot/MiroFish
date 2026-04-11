#!/usr/bin/env python3
"""
YouTube Video Monitor
====================
Check for new videos from subscribed channels, download transcripts,
and notify via Telegram.

Features:
1. Add/remove channels via Telegram bot commands
2. Check RSS feed for new videos
3. Download transcript (YouTube captions → Whisper fallback)
4. Download video file
5. Send Telegram notification
6. Track downloaded videos to avoid duplicates

Author: 蝦仔
Date: 2026-03-18
"""

import json
import os
import sys
import re
import subprocess
import requests
from datetime import datetime, timedelta
from pathlib import Path
import xml.etree.ElementTree as ET

# ============== CONFIG ==============

BASE_DIR = Path.home() / "gemini" / "youtube_downloads"
CONFIG_FILE = BASE_DIR / "config.json"
DOWNLOADED_FILE = BASE_DIR / "downloaded.json"
ARCHIVE_FILE = BASE_DIR / "download_archive.txt"
TRANSCRIPT_DIR = BASE_DIR / "transcripts"
LOG_FILE = BASE_DIR / "monitor.log"

# ============== HELPERS ==============

def log(msg):
    """Log message with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def load_config():
    """Load config.json"""
    with open(CONFIG_FILE) as f:
        return json.load(f)

def save_config(config):
    """Save config.json"""
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def load_downloaded():
    """Load downloaded.json"""
    if DOWNLOADED_FILE.exists():
        with open(DOWNLOADED_FILE) as f:
            return json.load(f)
    return {"videos": []}

def save_downloaded(data):
    """Save downloaded.json"""
    with open(DOWNLOADED_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def is_downloaded(video_id, downloaded_data):
    """Check if video was already downloaded"""
    # Check in downloaded.json
    for v in downloaded_data.get("videos", []):
        if v.get("video_id") == video_id:
            return True
    # Check in download_archive.txt (yt-dlp archive)
    if ARCHIVE_FILE.exists():
        with open(ARCHIVE_FILE) as f:
            if f"youtube {video_id}" in f.read():
                return True
    return False

def send_telegram(chat_id, text):
    """Send message to Telegram"""
    config = load_config()
    bot_token = config["telegram"]["bot_token"]
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.json()
    except Exception as e:
        log(f"Telegram send error: {e}")
        return None

# ============== RSS CHECK ==============

def get_channel_rss(channel_id):
    """Get RSS feed URL for channel ID"""
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

def check_rss_by_id(channel_id, channel_name, hours=24):
    """Check RSS feed for new videos from last N hours using channel ID"""
    rss_url = get_channel_rss(channel_id)
    
    try:
        r = requests.get(rss_url, timeout=10)
        if r.status_code != 200:
            log(f"RSS fetch failed for {channel_name}: {r.status_code}")
            return []
        
        root = ET.fromstring(r.text)
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "yt": "http://www.youtube.com/xml/schemas/2015",
            "media": "http://search.yahoo.com/mrss/"
        }
        
        cutoff = datetime.now() - timedelta(hours=hours)
        new_videos = []
        
        for entry in root.findall("atom:entry", ns):
            published = entry.find("atom:published", ns)
            if published is None:
                continue
            
            pub_date = datetime.fromisoformat(published.text.replace("Z", "+00:00"))
            if pub_date.replace(tzinfo=None) < cutoff:
                continue
            
            video_id = entry.find("yt:videoId", ns)
            title = entry.find("atom:title", ns)
            link = entry.find("atom:link", ns)
            
            if video_id is not None:
                new_videos.append({
                    "video_id": video_id.text,
                    "title": title.text if title is not None else "Unknown",
                    "published": published.text,
                    "url": link.attrib.get("href", f"https://youtube.com/watch?v={video_id.text}")
                })
        
        return new_videos
    
    except Exception as e:
        log(f"RSS check error for {channel_name}: {e}")
        return []

# ============== TRANSCRIPT ==============

def get_youtube_transcript(video_id, cookies_file=None):
    """Try to get transcript from YouTube captions"""
    try:
        cmd = [
            "yt-dlp",
            "--cookies", cookies_file if cookies_file else str(BASE_DIR / "cookies.txt"),
            "--write-auto-sub",
            "--sub-lang", "zh,zh-Hans,zh-Hant,en,zh-TW",
            "--sub-format", "vtt",
            "--skip-download",
            "--no-overwrites",
            "-o", str(TRANSCRIPT_DIR / f"{video_id}"),
            f"https://youtube.com/watch?v={video_id}"
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        # Look for downloaded subtitle file
        for ext in [".zh-Hans.vtt", ".zh-Hant.vtt", ".zh.vtt", ".en.vtt", ".vtt"]:
            vtt_file = TRANSCRIPT_DIR / f"{video_id}{ext}"
            if vtt_file.exists():
                return parse_vtt(vtt_file)
        
        return None
    
    except Exception as e:
        log(f"YouTube transcript error for {video_id}: {e}")
        return None

def parse_vtt(vtt_file):
    """Parse VTT file to plain text"""
    try:
        with open(vtt_file, encoding="utf-8") as f:
            content = f.read()
        
        # Remove VTT header and timestamps
        lines = content.split("\n")
        text_lines = []
        seen = set()
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith("WEBVTT") or line.startswith("Kind:") or \
               line.startswith("Language:") or "-->" in line or line.isdigit():
                continue
            # Remove HTML tags
            clean = re.sub(r"<[^>]+>", "", line)
            if clean and clean not in seen:
                seen.add(clean)
                text_lines.append(clean)
        
        return "\n".join(text_lines)
    
    except Exception as e:
        log(f"VTT parse error: {e}")
        return None

def whisper_transcribe(video_id, cookies_file=None):
    """Download audio and transcribe with Whisper"""
    try:
        audio_file = TRANSCRIPT_DIR / f"{video_id}.mp3"
        
        # Download audio only
        cmd_download = [
            "yt-dlp",
            "--cookies", cookies_file if cookies_file else str(BASE_DIR / "cookies.txt"),
            "-x",
            "--audio-format", "mp3",
            "-o", str(audio_file),
            f"https://youtube.com/watch?v={video_id}"
        ]
        
        log(f"Downloading audio for {video_id}...")
        subprocess.run(cmd_download, capture_output=True, text=True, timeout=300)
        
        if not audio_file.exists():
            return None
        
        # Transcribe with whisper
        cmd_whisper = [
            "whisper",
            str(audio_file),
            "--model", "base",
            "--language", "zh",
            "--output_format", "txt",
            "--output_dir", str(TRANSCRIPT_DIR)
        ]
        
        log(f"Transcribing {video_id} with Whisper...")
        subprocess.run(cmd_whisper, capture_output=True, text=True, timeout=600)
        
        # Read transcript
        txt_file = TRANSCRIPT_DIR / f"{audio_file.stem}.txt"
        if txt_file.exists():
            with open(txt_file, encoding="utf-8") as f:
                return f.read()
        
        return None
    
    except Exception as e:
        log(f"Whisper error for {video_id}: {e}")
        return None

def get_transcript(video_id):
    """Get transcript - YouTube captions first, then Whisper"""
    transcript = get_youtube_transcript(video_id)
    if transcript:
        log(f"Got YouTube captions for {video_id}")
        return transcript, "youtube"
    
    transcript = whisper_transcribe(video_id)
    if transcript:
        log(f"Got Whisper transcript for {video_id}")
        return transcript, "whisper"
    
    return None, None

# ============== DOWNLOAD VIDEO ==============

def download_video(video_id, channel_name):
    """Download video file"""
    try:
        output_dir = BASE_DIR / channel_name
        output_dir.mkdir(parents=True, exist_ok=True)
        
        cmd = [
            "yt-dlp",
            "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]",
            "--merge-output-format", "mp4",
            "--write-thumbnail",
            "-o", str(output_dir / "%(title)s [%(id)s].%(ext)s"),
            f"https://youtube.com/watch?v={video_id}"
        ]
        
        log(f"Downloading video {video_id}...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        return result.returncode == 0
    
    except Exception as e:
        log(f"Download error for {video_id}: {e}")
        return False

# ============== MAIN ==============

def check_all_channels():
    """Main function: check all channels for new videos"""
    config = load_config()
    downloaded = load_downloaded()
    chat_id = config["telegram"]["chat_id"]
    
    if chat_id == "MIROFISH_CHAT_ID_PLACEHOLDER":
        log("ERROR: Chat ID not configured! Update config.json")
        return
    
    log("=== YouTube Monitor Started ===")
    
    total_new = 0
    
    for channel in config["channels"]:
        name = channel["name"]
        handle = channel["handle"]
        channel_id = channel.get("channel_id", "")
        
        log(f"Checking {name} ({handle})...")
        
        new_videos = check_rss_by_id(channel_id, name, hours=24)
        
        if not new_videos:
            log(f"  No new videos from {name}")
            continue
        
        for video in new_videos:
            video_id = video["video_id"]
            
            if is_downloaded(video_id, downloaded):
                log(f"  Already downloaded: {video['title']}")
                continue
            
            log(f"  New video: {video['title']}")
            total_new += 1
            
            # Get transcript
            transcript, source = get_transcript(video_id)
            
            # Save transcript
            if transcript:
                transcript_file = TRANSCRIPT_DIR / f"{video_id}.txt"
                with open(transcript_file, "w", encoding="utf-8") as f:
                    f.write(f"Title: {video['title']}\n")
                    f.write(f"URL: {video['url']}\n")
                    f.write(f"Channel: {name}\n")
                    f.write(f"Date: {video['published']}\n")
                    f.write(f"Transcript source: {source}\n")
                    f.write("=" * 50 + "\n\n")
                    f.write(transcript)
                log(f"  Transcript saved: {transcript_file}")
            
            # Download video
            download_video(video_id, name)
            
            # Send notification
            notification = f"""🎬 <b>New Video!</b>

📺 <b>{name}</b>
{video['title']}

🔗 {video['url']}
📝 Transcript: {'✅ ' + source if transcript else '❌ Not available'}"""

            send_telegram(chat_id, notification)
            
            # Mark as downloaded
            downloaded["videos"].append({
                "video_id": video_id,
                "title": video["title"],
                "channel": name,
                "url": video["url"],
                "downloaded_at": datetime.now().isoformat(),
                "has_transcript": transcript is not None,
                "transcript_source": source
            })
    
    save_downloaded(downloaded)
    log(f"=== Done. Found {total_new} new videos ===")

# ============== TELEGRAM BOT ==============

def run_bot():
    """Run Telegram bot to handle commands"""
    config = load_config()
    bot_token = config["telegram"]["bot_token"]
    offset = 0
    
    log("Telegram bot started...")
    
    while True:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
            r = requests.get(url, params={"offset": offset, "timeout": 30}, timeout=35)
            data = r.json()
            
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                
                message = update.get("message", {})
                text = message.get("text", "")
                chat_id = message.get("chat", {}).get("id")
                
                if not text or not chat_id:
                    continue
                
                handle_command(text, chat_id, config)
        
        except Exception as e:
            log(f"Bot error: {e}")
            import time
            time.sleep(5)

def handle_command(text, chat_id, config):
    """Handle bot commands"""
    parts = text.strip().split()
    cmd = parts[0].lower()
    
    if cmd == "/add_channel" and len(parts) >= 2:
        handle = parts[1]
        if not handle.startswith("@"):
            handle = "@" + handle
        
        # Check if already exists
        for ch in config["channels"]:
            if ch["handle"].lower() == handle.lower():
                send_telegram(chat_id, f"⚠️ Channel {handle} already exists!")
                return
        
        # Get channel ID
        channel_id = get_channel_id_from_rss(handle)
        
        config["channels"].append({
            "name": handle.replace("@", ""),
            "handle": handle,
            "channel_id": channel_id or "unknown"
        })
        save_config(config)
        send_telegram(chat_id, f"✅ Added channel: {handle}")
    
    elif cmd == "/remove_channel" and len(parts) >= 2:
        handle = parts[1]
        if not handle.startswith("@"):
            handle = "@" + handle
        
        original_len = len(config["channels"])
        config["channels"] = [ch for ch in config["channels"] if ch["handle"].lower() != handle.lower()]
        
        if len(config["channels"]) < original_len:
            save_config(config)
            send_telegram(chat_id, f"✅ Removed channel: {handle}")
        else:
            send_telegram(chat_id, f"⚠️ Channel {handle} not found!")
    
    elif cmd == "/list_channels":
        if not config["channels"]:
            send_telegram(chat_id, "📭 No channels configured.")
            return
        
        msg = "📺 <b>Monitored Channels:</b>\n\n"
        for i, ch in enumerate(config["channels"], 1):
            msg += f"{i}. {ch['name']} ({ch['handle']})\n"
        send_telegram(chat_id, msg)
    
    elif cmd == "/check_now":
        send_telegram(chat_id, "🔍 Checking for new videos...")
        check_all_channels()
    
    elif cmd == "/help":
        send_telegram(chat_id, """🤖 <b>YouTube Monitor Bot</b>

Commands:
/add_channel @handle - Add channel
/remove_channel @handle - Remove channel
/list_channels - List channels
/check_now - Check now
/help - Show help""")

# ============== CLI ==============

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python youtube_monitor.py check    - Check for new videos")
        print("  python youtube_monitor.py bot      - Run Telegram bot")
        print("  python youtube_monitor.py add @handle - Add channel")
        print("  python youtube_monitor.py remove @handle - Remove channel")
        print("  python youtube_monitor.py list     - List channels")
        sys.exit(1)
    
    action = sys.argv[1]
    
    if action == "check":
        check_all_channels()
    elif action == "bot":
        run_bot()
    elif action == "add" and len(sys.argv) >= 3:
        config = load_config()
        handle = sys.argv[2]
        if not handle.startswith("@"):
            handle = "@" + handle
        config["channels"].append({
            "name": handle.replace("@", ""),
            "handle": handle,
            "channel_id": "unknown"
        })
        save_config(config)
        print(f"✅ Added: {handle}")
    elif action == "remove" and len(sys.argv) >= 3:
        config = load_config()
        handle = sys.argv[2]
        if not handle.startswith("@"):
            handle = "@" + handle
        config["channels"] = [ch for ch in config["channels"] if ch["handle"].lower() != handle.lower()]
        save_config(config)
        print(f"✅ Removed: {handle}")
    elif action == "list":
        config = load_config()
        print("📺 Monitored Channels:")
        for ch in config["channels"]:
            print(f"  - {ch['name']} ({ch['handle']})")
    else:
        print(f"Unknown command: {action}")
