#!/usr/bin/env python3
"""
Single YouTube video download and transcription wrapper.
Usage: python3 download_single_video.py <youtube_url>
"""
import subprocess, sys, json, os, re, shutil
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# Configuration — paths relative to monorepo root
_SCRIPT_DIR = Path(__file__).resolve().parent
_MONO_ROOT = _SCRIPT_DIR.parent.parent.parent
WORK_DIR = _MONO_ROOT / "data" / "raw" / "media" / "youtube_downloads"
TRANSCRIPT_DIR = WORK_DIR / "transcripts"
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
YT_DLP = "yt-dlp"
COOKIES_FILE = WORK_DIR / "cookies.txt"

def extract_video_id(url):
    """Extract video ID from YouTube URL."""
    parsed = urlparse(url)
    if parsed.hostname in ['www.youtube.com', 'youtube.com']:
        if parsed.path == '/watch':
            return parse_qs(parsed.query)['v'][0]
        elif parsed.path.startswith('/embed/'):
            return parsed.path.split('/')[2]
        elif parsed.path.startswith('/v/'):
            return parsed.path.split('/')[2]
    elif parsed.hostname == 'youtu.be':
        return parsed.path[1:]
    raise ValueError(f"Could not extract video ID from URL: {url}")

def download_video(video_id, folder):
    """Download single video using yt-dlp."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"Downloading video: {url}")
    print(f"Target folder: {folder}")

    # Ensure folder exists
    folder.mkdir(parents=True, exist_ok=True)

    # Download command with cookies
    cmd = f'{YT_DLP} --cookies "{COOKIES_FILE}" -o "{folder}/%(title)s [%(id)s].%(ext)s" "{url}"'
    print(f"Executing: {cmd}")

    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
    if r.returncode == 0:
        print("✅ Video downloaded successfully")
        return True
    else:
        print(f"❌ Download failed: {r.stderr[-200:]}")
        return False

def extract_audio(video_id, folder):
    """Extract audio from video file."""
    # Find the downloaded video file
    video_file = None
    for f in folder.glob(f"*{video_id}*"):
        if f.suffix in [".mp4", ".webm", ".mkv"]:
            video_file = f
            break

    if not video_file:
        print(f"❌ Could not find video file for {video_id}")
        return None

    print(f"Extracting audio from: {video_file.name}")
    wav_path = folder / f"{video_id}.wav"

    r = subprocess.run([
        FFMPEG, "-i", str(video_file),
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        "-y", str(wav_path)
    ], capture_output=True, text=True, timeout=300)

    if r.returncode == 0:
        print(f"✅ Audio extracted: {wav_path.name}")
        return wav_path
    else:
        print(f"❌ Audio extraction failed: {r.stderr[-200:]}")
        return None

def transcribe_video(video_id, folder):
    """Transcribe video with Whisper."""
    # Check if transcript already exists
    transcript_path = TRANSCRIPT_DIR / f"{video_id}.txt"
    if transcript_path.exists() and transcript_path.stat().st_size > 1000:
        print(f"✅ Transcript already exists: {transcript_path.name}")
        return True

    # Extract audio first
    wav_path = extract_audio(video_id, folder)
    if not wav_path:
        return False

    print(f"Transcribing audio with Whisper...")

    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8", cpu_threads=4)
        segments, info = model.transcribe(str(wav_path), beam_size=1, vad_filter=True)
        texts = [s.text.strip() for s in segments if s.text.strip()]
        content = " ".join(texts)

        # Save transcript
        TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
        transcript_path.write_text(content, encoding="utf-8")

        # Clean up temporary WAV file
        if wav_path.exists():
            wav_path.unlink()

        print(f"✅ Transcription complete: {len(content)} characters")
        return len(content) > 500
    except Exception as e:
        print(f"❌ Transcription failed: {e}")
        # Clean up WAV file even on failure
        if wav_path.exists():
            wav_path.unlink()
        return False

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 download_single_video.py <youtube_url>")
        print("Example: python3 download_single_video.py https://www.youtube.com/watch?v=80ULpxa8ipI")
        sys.exit(1)

    url = sys.argv[1]
    try:
        video_id = extract_video_id(url)
        print(f"🎯 Extracted video ID: {video_id}")
    except Exception as e:
        print(f"❌ {e}")
        sys.exit(1)

    # Create dedicated folder for this video
    video_folder = WORK_DIR / video_id
    print(f"📁 Creating video folder: {video_folder}")

    # Check if video already exists
    if any(video_folder.glob(f"*{video_id}*")):
        print(f"⚠️  Video already exists in {video_folder}")
        proceed = input("Do you want to re-download? (y/N): ").strip().lower()
        if proceed != 'y':
            print("Skipping download...")
        else:
            download_video(video_id, video_folder)
    else:
        # Download video
        if not download_video(video_id, video_folder):
            sys.exit(1)

    # Transcribe video
    if transcribe_video(video_id, video_folder):
        print(f"\n🎉 Success! Video processed:")
        print(f"   Video folder: {video_folder}")
        print(f"   Transcript: {TRANSCRIPT_DIR}/{video_id}.txt")
    else:
        print("❌ Transcription failed. Please check logs.")
        sys.exit(1)

if __name__ == "__main__":
    main()