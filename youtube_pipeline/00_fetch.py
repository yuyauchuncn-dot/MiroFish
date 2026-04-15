#!/usr/bin/env python3
"""MiroFish Pipeline Step 0 — Unified content fetcher via monofetchers.

Replaces 01_download.sh + 02_transcribe.py for:
  - YouTube URLs (metadata + subtitles/Whisper)
  - Article URLs (trafilatura extraction)
  - Local .txt files (direct read)
  - Local .mp4 files (yt-dlp metadata + Whisper transcription)

Falls back gracefully when monofetchers cannot handle the input.
Outputs to /tmp/mirofish_step.env: VIDEO_ID, CHANNEL, VIDEO_PATH,
  TRANSCRIPT_TEXT, TRANSCRIPT_PATH, INPUT_TYPE, USE_V4
"""

import json
import re
import sys
import tempfile
from pathlib import Path

# Allow importing monofetchers from monorepo root
_script_dir = Path(__file__).resolve().parent
_mono_root = _script_dir.parent.parent  # youtube_pipeline -> mirofish -> monorepo
sys.path.insert(0, str(_mono_root))

from monofetchers import fetch, detect_type
from monofetchers.config import YOUTUBE_COOKIES_FILE, TRANSCRIPTS_DIR
from monofetchers.youtube.fetcher import (
    _extract_video_id, _run_yt_dlp, _vtt_to_txt, _transcribe_with_whisper,
)

STEP_ENV = "/tmp/mirofish_step.env"


def load_step_env():
    env = {}
    p = Path(STEP_ENV)
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k] = v
    return env


def save_step_env(env):
    with open(STEP_ENV, "w", encoding="utf-8") as f:
        for k, v in env.items():
            f.write(f"{k}={v}\n")


def _handle_local_mp4(mp4_path: str) -> dict:
    """Handle local .mp4: extract metadata via yt-dlp, transcribe with Whisper.

    Reuses monofetchers internal functions (_run_yt_dlp, _vtt_to_txt, _transcribe_with_whisper).
    """
    p = Path(mp4_path)
    if not p.exists():
        return {"success": False, "error": f"File not found: {mp4_path}"}

    stem = p.stem
    m = re.search(r'\[([^\]]+)\]$', stem)
    video_id = m.group(1) if m else None

    if not video_id:
        import hashlib
        video_id = hashlib.md5(str(p.resolve()).encode()).hexdigest()[:11]

    channel = p.parent.name if p.parent.name != p.name else "未分类"
    output_dir = Path(TRANSCRIPTS_DIR) / channel / video_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get metadata + subtitles (skip download since we have the file)
    video_info, vtt_path, _ = _run_yt_dlp(
        video_id, output_dir, YOUTUBE_COOKIES_FILE, skip_download=True,
    )

    transcript_text = ""
    local_files = []
    transcription_method = "none"

    # Convert VTT if available
    if vtt_path:
        transcript_text = _vtt_to_txt(vtt_path)
        txt_path = output_dir / f"{video_id}_transcript.txt"
        txt_path.write_text(transcript_text, encoding="utf-8")
        local_files.append(str(txt_path))
        transcription_method = "subtitle"

    # Whisper fallback
    if not transcript_text:
        print(f"  No subtitles found, transcribing with Whisper...")
        transcript_text = _transcribe_with_whisper(
            p, output_dir, video_id, language="zh",
        )
        if transcript_text:
            txt_path = output_dir / f"{video_id}_transcript.txt"
            local_files.append(str(txt_path))
            transcription_method = "whisper"

    title = (video_info or {}).get("title", stem) if video_info else stem
    uploader = (video_info or {}).get("uploader", channel) if video_info else channel

    return {
        "success": bool(transcript_text),
        "source_type": "youtube",
        "cleaned_text": transcript_text,
        "metadata": {
            "video_id": video_id,
            "title": title,
            "channel": uploader,
            "transcription_method": transcription_method,
        },
        "local_files": local_files + [str(p)],
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python 00_fetch.py <youtube_url | article_url | local.txt | local.mp4>")
        sys.exit(1)

    inp = sys.argv[1]
    use_v4 = "--v4" in sys.argv

    print(f"[Step 0] Fetching: {inp}")

    # ── Route ──────────────────────────────────────────────────────────
    source_type = detect_type(inp)
    print(f"  Detected type: {source_type}")

    result = None

    if source_type in ("local_txt", "article"):
        # monofetchers handles directly
        result = fetch(inp)

    elif source_type == "youtube":
        result = fetch(inp)

    elif inp.endswith(".mp4") and Path(inp).exists():
        # Local .mp4 — special handling (detect_type returns "unknown")
        print(f"  Handling local .mp4 with yt-dlp metadata + transcription...")
        result_data = _handle_local_mp4(inp)
        # Wrap as a dict-compatible result
        result = type("Result", (), {
            "success": result_data["success"],
            "source_type": result_data["source_type"],
            "cleaned_text": result_data["cleaned_text"],
            "metadata": result_data["metadata"],
            "local_files": result_data["local_files"],
            "error": result_data.get("error"),
        })()

    else:
        print(f"  Unsupported input type — falling back to legacy pipeline")
        save_step_env({"FALLBACK": "true", "INPUT": inp, "USE_V4": str(use_v4).lower()})
        sys.exit(0)

    # ── Handle failure → fallback ──────────────────────────────────────
    if result is None or not result.success:
        error = getattr(result, "error", "Unknown error") if result else "No result"
        print(f"  Fetch failed: {error} — falling back to legacy pipeline")
        save_step_env({"FALLBACK": "true", "INPUT": inp, "USE_V4": str(use_v4).lower()})
        sys.exit(0)

    # ── Write results to step env ──────────────────────────────────────
    meta = result.metadata
    channel = meta.get("channel", "Unknown")
    video_id = meta.get("video_id", "unknown")

    # Also write transcript to a file for backward compat
    txt_path = ""
    if result.cleaned_text:
        txt_dir = Path(TRANSCRIPTS_DIR) / channel / video_id
        txt_dir.mkdir(parents=True, exist_ok=True)
        txt_file = txt_dir / f"{video_id}_transcript.txt"
        txt_file.write_text(result.cleaned_text, encoding="utf-8")
        txt_path = str(txt_file)

    env = {
        "VIDEO_ID": video_id,
        "CHANNEL": channel,
        "VIDEO_PATH": meta.get("video_path", inp),
        "TRANSCRIPT_TEXT": result.cleaned_text,
        "INPUT_TYPE": result.source_type,
        "USE_V4": str(use_v4).lower(),
        "TRANSCRIPT_PATH": txt_path,
    }

    save_step_env(env)

    print(f"  Video ID: {video_id}")
    print(f"  Channel: {channel}")
    print(f"  Transcript: {len(result.cleaned_text)} chars")
    print(f"  Method: {meta.get('transcription_method', 'N/A')}")
    print("[Step 0] Done — env written to /tmp/mirofish_step.env")


if __name__ == "__main__":
    main()
