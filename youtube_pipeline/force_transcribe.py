#!/usr/bin/env python3
"""
Force transcription of existing video file.
"""
import sys, os, shutil
from pathlib import Path

# Configuration — paths relative to monorepo root
_SCRIPT_DIR = Path(__file__).resolve().parent
_MONO_ROOT = _SCRIPT_DIR.parent.parent.parent
WORK_DIR = _MONO_ROOT / "data" / "raw" / "media" / "youtube_downloads"
TRANSCRIPT_DIR = WORK_DIR / "transcripts"
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"

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

    import subprocess
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
        transcript_path = TRANSCRIPT_DIR / f"{video_id}.txt"
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
        print("Usage: python3 force_transcribe.py <video_id>")
        sys.exit(1)

    video_id = sys.argv[1].strip()
    video_folder = WORK_DIR / video_id

    if not video_folder.exists():
        print(f"❌ Video folder does not exist: {video_folder}")
        sys.exit(1)

    if transcribe_video(video_id, video_folder):
        print(f"\n🎉 Success! Transcript generated:")
        print(f"   Transcript: {TRANSCRIPT_DIR}/{video_id}.txt")
    else:
        print("❌ Transcription failed. Please check logs.")
        sys.exit(1)

if __name__ == "__main__":
    main()