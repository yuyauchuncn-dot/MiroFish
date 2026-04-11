#!/usr/bin/env python3
"""Transcribe YouTube videos using faster-whisper with chunking to avoid truncation."""
import sys
import os
import subprocess
import json
from pathlib import Path

FFMPEG = "/opt/homebrew/bin/ffmpeg"

def extract_audio(mp4_path, wav_path):
    """Extract audio from video file as 16kHz mono WAV."""
    if wav_path.exists():
        return True
    try:
        subprocess.run([
            FFMPEG, '-i', str(mp4_path), '-vn', '-acodec', 'pcm_s16le',
            '-ar', '16000', '-ac', '1', '-y', str(wav_path)
        ], capture_output=True, timeout=120, check=True)
        return True
    except Exception as e:
        print(f"  Audio extraction failed: {e}")
        return False

def transcribe_video(video_path, output_dir, model_size="base"):
    """Transcribe a single video file."""
    from faster_whisper import WhisperModel
    
    video_path = Path(video_path)
    stem = video_path.stem
    vtt_path = output_dir / f"{stem}.vtt"
    txt_path = output_dir / f"{stem}.txt"
    
    if vtt_path.exists() and txt_path.exists():
        print(f"  SKIP (already exists): {stem}")
        return True
    
    print(f"  Loading model: {model_size}...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    
    # Extract audio
    wav_path = Path(f"/tmp/{stem}.wav")
    print(f"  Extracting audio from {video_path.name}...")
    if not extract_audio(video_path, wav_path):
        return False
    
    file_size_mb = wav_path.stat().st_size / 1024 / 1024
    print(f"  Audio: {file_size_mb:.0f}MB, transcribing...")
    
    try:
        segments, info = model.transcribe(
            str(wav_path),
            beam_size=1,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            word_timestamps=False
        )
        
        vtt_lines = ["WEBVTT\n"]
        txt_lines = []
        seg_idx = 1
        
        for segment in segments:
            start = segment.start
            end = segment.end
            text = segment.text.strip()
            if not text:
                continue
                
            # Format VTT timestamps
            def fmt_ts(s):
                h = int(s // 3600)
                m = int((s % 3600) // 60)
                sec = int(s % 60)
                ms = int((s % 1) * 1000)
                return f"{h:02d}:{m:02d}:{sec:02d}.{ms:03d}"
            
            vtt_lines.append(f"{seg_idx}")
            vtt_lines.append(f"{fmt_ts(start)} --> {fmt_ts(end)}")
            vtt_lines.append(text)
            vtt_lines.append("")
            txt_lines.append(text)
            seg_idx += 1
        
        if len(txt_lines) < 5:
            print(f"  WARNING: Only {len(txt_lines)} segments transcribed")
            return False
        
        # Save VTT
        vtt_path.parent.mkdir(parents=True, exist_ok=True)
        vtt_path.write_text("\n".join(vtt_lines), encoding="utf-8")
        
        # Save txt
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        txt_path.write_text(" ".join(txt_lines), encoding="utf-8")
        
        print(f"  DONE: {len(txt_lines)} segments, {len(' '.join(txt_lines))} chars")
        
        # Cleanup
        wav_path.unlink(missing_ok=True)
        return True
        
    except Exception as e:
        print(f"  ERROR: {e}")
        wav_path.unlink(missing_ok=True)
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: transcribe.py <video_file> <output_dir> [model_size]")
        sys.exit(1)
    
    video_file = sys.argv[1]
    output_dir = Path(sys.argv[2])
    model_size = sys.argv[3] if len(sys.argv) > 3 else "base"
    
    success = transcribe_video(video_file, output_dir, model_size)
    sys.exit(0 if success else 1)
