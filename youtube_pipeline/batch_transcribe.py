#!/usr/bin/env python3
"""Batch transcribe videos - processes all videos missing transcripts."""
import sys
import os
import shutil
import subprocess
from pathlib import Path
import time

# Import path configuration from config module
_script_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(_script_dir))
from config import YOUTUBE_DIR, TRANSCRIPTS_DIR
sys.path.pop(0)

FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
OUT_DIR = Path(TRANSCRIPTS_DIR)
OUT_DIR.mkdir(parents=True, exist_ok=True)

VIDEOS = [
    "mA61u_Eg8ag", "e2eXLTK13-8", "iL8IbdhdWhY", "KaMxAJVcdZQ",
    "8FG_1es_GkY", "K16p8aJfJUM", "WZoVmOmfFC4", "PdJEZcRV-UY",
    "j08V-mkuWPk", "rN7nlAjfZDM", "PnrvQL2T_ck", "ir2NMBmH4yM",
    "_lyWqelvhIc", "tZ3TbJqvG4w", "YKeVu9SlqFE", "B6Sw8KXVX44",
    "fSzbgDvzDlU", "EDIfXvPDO3Y", "1ZsjCdluO6c"
]

def find_video(vid):
    """Find video file by ID - recursive search in YOUTUBE_DIR."""
    for f in YOUTUBE_DIR.rglob(f"*[{vid}]*"):
        if f.suffix in ['.mp4', '.mkv', '.webm']:
            return f
    return None

def transcribe_video(video_path, output_path):
    """Transcribe using faster-whisper."""
    from faster_whisper import WhisperModel

    wav_path = f"/tmp/{video_path.stem}.wav"
    
    r = subprocess.run([FFMPEG, "-i", str(video_path), "-vn", "-acodec", "pcm_s16le",
                        "-ar", "16000", "-ac", "1", "-y", wav_path],
                       capture_output=True, timeout=600)
    if r.returncode != 0:
        return {"status": "error", "error": f"ffmpeg failed: {r.stderr.decode()[-300:]}"}

    model = WhisperModel("base", device="cpu", compute_type="int8", cpu_threads=4)
    segments, info = model.transcribe(wav_path, beam_size=1, vad_filter=True)
    texts = [s.text.strip() for s in segments if s.text.strip()]
    content = " ".join(texts)
    output_path.write_text(content, encoding="utf-8")

    if os.path.exists(wav_path):
        os.remove(wav_path)

    return {"status": "done", "segments": len(texts), "chars": len(content)}

def main():
    total = len(VIDEOS)
    done_count = 0
    skipped = 0
    errors = 0
    
    for i, vid in enumerate(VIDEOS):
        print(f"\n[{i+1}/{total}] Processing {vid}...")
        sys.stdout.flush()
        
        out_path = OUT_DIR / f"{vid}.txt"
        
        if out_path.exists() and out_path.stat().st_size > 500:
            print(f"  ⏭️  Already transcribed ({out_path.stat().st_size} chars), skipping")
            skipped += 1
            done_count += 1
            continue
        
        video_path = find_video(vid)
        if not video_path:
            print(f"  ❌ Video file not found!")
            errors += 1
            continue
        
        print(f"  📹 Found: {video_path.name}")
        sys.stdout.flush()
        
        t0 = time.time()
        result = transcribe_video(video_path, out_path)
        elapsed = time.time() - t0
        
        if result["status"] == "done":
            print(f"  ✅ Done: {result['segments']} segments, {result['chars']} chars ({elapsed:.1f}s)")
            done_count += 1
        else:
            print(f"  ❌ Error: {result.get('error', 'unknown')}")
            errors += 1
        
        # Clean up wav
        wav = f"/tmp/{vid}.wav"
        if os.path.exists(wav):
            os.remove(wav)
        
        sys.stdout.flush()
    
    print(f"\n{'='*50}")
    print(f"Total: {total} | Done: {done_count} | Skipped: {skipped} | Errors: {errors}")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
