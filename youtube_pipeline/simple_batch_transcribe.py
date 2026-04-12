#!/usr/bin/env python3
"""Simple batch transcribe for lao lihai videos."""
import os
import sys
import shutil
import subprocess
from pathlib import Path

# Import path configuration from config module
_script_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(_script_dir))
from config import YOUTUBE_DIR
sys.path.pop(0)

FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
VIDEO_DIR = Path(YOUTUBE_DIR) / "老厉害"
OUTPUT_DIR = Path(YOUTUBE_DIR) / "transcripts"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Video IDs to transcribe
VIDEO_IDS = [
    ("71VeKWYleyA", "野村美银巴克莱"),
    ("A3Hxv_GTaac", "花旗研报"),
    ("mHT6SnN0FvU", "高盛野村"),
    ("zPtU7BXJTu4", "瑞银花旗"),
    ("b_x6s2WZ054", "荣鼎"),
    ("hd3I705fWZc", "高盛"),
]

def find_video(vid_id):
    """Find video by ID."""
    for f in VIDEO_DIR.iterdir():
        if f.is_file() and vid_id in f.name and f.suffix == '.mp4':
            return f
    return None

def extract_audio(video_path, wav_path):
    """Extract audio from video."""
    if wav_path.exists():
        print(f"  Audio already exists, skipping extraction")
        return True
    print(f"  Extracting audio...")
    result = subprocess.run([
        FFMPEG, '-i', str(video_path), '-vn', '-acodec', 'pcm_s16le',
        '-ar', '16000', '-ac', '1', '-y', str(wav_path)
    ], capture_output=True, timeout=300)
    if result.returncode != 0:
        print(f"  FFmpeg error: {result.stderr.decode()[-200:]}")
        return False
    print(f"  Audio extracted: {wav_path.stat().st_size / 1024 / 1024:.0f}MB")
    return True

def transcribe_audio(wav_path, txt_path):
    """Transcribe audio with faster-whisper."""
    from faster_whisper import WhisperModel
    
    print(f"  Loading whisper model...")
    model = WhisperModel("base", device="cpu", compute_type="int8")
    
    print(f"  Transcribing...")
    segments, info = model.transcribe(
        str(wav_path),
        beam_size=1,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500)
    )
    
    texts = []
    for seg in segments:
        if seg.text.strip():
            texts.append(seg.text.strip())
    
    if len(texts) < 5:
        print(f"  WARNING: Only {len(texts)} segments")
        return False
    
    content = " ".join(texts)
    txt_path.write_text(content, encoding="utf-8")
    print(f"  DONE: {len(texts)} segments, {len(content)} chars")
    return True

def main():
    print(f"Starting batch transcription of {len(VIDEO_IDS)} videos")
    print(f"Output directory: {OUTPUT_DIR}")
    print()
    
    for i, (vid_id, name) in enumerate(VIDEO_IDS):
        print(f"\n=== VIDEO {i+1}/6: {vid_id} ({name}) ===")
        
        video_path = find_video(vid_id)
        if not video_path:
            print(f"  ERROR: Video not found!")
            continue
        
        print(f"  Found: {video_path.name[:60]}...")
        
        # Output file path
        txt_path = OUTPUT_DIR / f"{video_path.stem}.txt"
        
        if txt_path.exists():
            print(f"  SKIP: Transcript already exists")
            continue
        
        # Extract audio
        wav_path = Path(f"/tmp/{vid_id}.wav")
        if not extract_audio(video_path, wav_path):
            continue
        
        # Transcribe
        success = transcribe_audio(wav_path, txt_path)
        
        # Cleanup
        if wav_path.exists():
            wav_path.unlink()
        
        if success:
            print(f"  ✓ Saved to: {txt_path.name}")
        else:
            print(f"  ✗ Failed")
    
    print(f"\n{'='*50}")
    print("BATCH TRANSCRIPTION COMPLETE")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
