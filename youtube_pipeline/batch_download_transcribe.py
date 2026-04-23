#!/usr/bin/env python3
"""
Batch download, transcribe, and prepare for MiroFish analysis.
Usage: python3 batch_download_transcribe.py <channel> [--transcribe] [--mirofish]
"""
import subprocess, sys, json, os, shutil
from pathlib import Path
from urllib.request import urlopen, Request
from xml.etree import ElementTree as ET

_SCRIPT_DIR = Path(__file__).resolve().parent
_MONO_ROOT = _SCRIPT_DIR.parent.parent.parent
WORK_DIR = _MONO_ROOT / "monodata" / "data" / "raw" / "media" / "youtube_downloads"
TRANSCRIPT_DIR = WORK_DIR / "transcripts"
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
YT_DLP = "yt-dlp"

# Channel configs
CHANNELS = {
    "laopowerful": {
        "channel_id": "UC8gZZWIWmBuCb_gzC8DUrvw",
        "folder": WORK_DIR / "老.powerful",
        "name": "老.powerful"
    },
    "henry": {
        "channel_id": "UC9KZAJODBZXwVbJje4SZg2A",
        "folder": WORK_DIR / "Henry 的慢思考",
        "name": "Henry 的慢思考"
    }
}

def get_rss_videos(channel_id):
    """Get videos from RSS feed."""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=30) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)
        ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
        videos = []
        for entry in root.findall("atom:entry", ns):
            video_id = entry.find("yt:videoId", ns).text
            title = entry.find("atom:title", ns).text
            videos.append({"id": video_id, "title": title, "url": f"https://www.youtube.com/watch?v={video_id}"})
        return videos
    except Exception as e:
        print(f"RSS fetch failed: {e}")
        return []

def check_local(folder, video_id):
    """Check if video exists locally."""
    for ext in [".mp4", ".webm", ".mp3", ".m4a"]:
        if list(folder.glob(f"*{video_id}*{ext}")):
            return True
    return False

def check_transcript(video_id):
    """Check if transcript exists."""
    txt = TRANSCRIPT_DIR / f"{video_id}.txt"
    if txt.exists() and txt.stat().st_size > 1000:
        return True
    return False

def download_video(video, folder):
    """Download video using yt-dlp."""
    print(f"  Downloading: {video['title'][:50]}...")
    cmd = f'{YT_DLP} --cookies {WORK_DIR}/cookies.txt -o "{folder}/%(title)s [%(id)s].%(ext)s" "{video["url"]}"'
    r = subprocess.run(cmd, shell=True, capture_output=True, timeout=600)
    if r.returncode == 0:
        print(f"  ✅ Downloaded")
        return True
    else:
        print(f"  ❌ Failed: {r.stderr.decode()[-200:]}")
        return False

def extract_audio(video_id, folder):
    """Extract audio from video file."""
    # Find video file
    video_file = None
    for f in folder.glob(f"*{video_id}*"):
        if f.suffix in [".mp4", ".webm"]:
            video_file = f
            break
    if not video_file:
        return None
    
    wav_path = f"/tmp/{video_id}.wav"
    r = subprocess.run([FFMPEG, "-i", str(video_file), "-vn", "-acodec", "pcm_s16le",
                        "-ar", "16000", "-ac", "1", "-y", wav_path],
                       capture_output=True, timeout=300)
    return wav_path if r.returncode == 0 else None

def transcribe_video(video_id, folder):
    """Transcribe video with Whisper."""
    if check_transcript(video_id):
        print(f"  Transcript exists, skipping")
        return True
    
    # Check for existing VTT
    for vtt in WORK_DIR.glob(f"*{video_id}*.vtt"):
        # Convert VTT to text
        text = vtt.read_text(encoding="utf-8")
        lines = [l.strip() for l in text.split("\n") if l.strip() and "-->" not in l and not l.startswith("WEBVTT")]
        import re
        clean = " ".join(re.sub(r'<[^>]+>', '', l) for l in lines if l)
        if len(clean) > 1000:
            (TRANSCRIPT_DIR / f"{video_id}.txt").write_text(clean, encoding="utf-8")
            print(f"  VTT→TXT: {len(clean)} chars")
            return True
    
    # Extract audio and whisper
    wav = extract_audio(video_id, folder)
    if not wav:
        print(f"  ❌ No audio extracted")
        return False
    
    from faster_whisper import WhisperModel
    model = WhisperModel("base", device="cpu", compute_type="int8", cpu_threads=4)
    segments, info = model.transcribe(wav, beam_size=1, vad_filter=True)
    texts = [s.text.strip() for s in segments if s.text.strip()]
    content = " ".join(texts)
    
    (TRANSCRIPT_DIR / f"{video_id}.txt").write_text(content, encoding="utf-8")
    if os.path.exists(wav):
        os.remove(wav)
    
    print(f"  Whisper: {len(content)} chars")
    return len(content) > 500

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("channel", choices=["laopowerful", "henry", "all"])
    parser.add_argument("--transcribe", action="store_true")
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    
    channels = CHANNELS if args.channel == "all" else {args.channel: CHANNELS[args.channel]}
    
    for name, config in channels.items():
        print(f"\n{'='*60}")
        print(f"Processing: {config['name']}")
        print(f"{'='*60}")
        
        # Get RSS
        videos = get_rss_videos(config["channel_id"])
        print(f"RSS videos: {len(videos)}")
        
        # Check local
        missing = [v for v in videos if not check_local(config["folder"], v["id"])]
        print(f"Missing locally: {len(missing)}")
        
        # Download
        if args.download and missing:
            print(f"\nDownloading {len(missing)} videos...")
            for v in missing:
                download_video(v, config["folder"])
        
        # Transcribe
        if args.transcribe:
            print(f"\nTranscribing...")
            for v in videos:
                if not check_transcript(v["id"]):
                    print(f"  {v['id']}: {v['title'][:40]}...")
                    transcribe_video(v["id"], config["folder"])
                else:
                    print(f"  {v['id']}: ✅ already has transcript")

if __name__ == "__main__":
    main()
