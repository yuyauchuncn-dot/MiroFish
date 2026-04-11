#!/bin/bash
# Master transcription script for both YouTube channels

set -e

WHISPER_BIN="/opt/homebrew/bin/whisper"
FFMPEG_BIN="/opt/homebrew/bin/ffmpeg"
BASE_DIR="'$(dirname "${BASH_SOURCE[0]}")/../../..'/data/raw/media/youtube_downloads"
VTT_CONVERTER="$BASE_DIR/vtt_to_txt.py"

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Check dependencies
if [ ! -f "$WHISPER_BIN" ]; then
    log_error "whisper not found at $WHISPER_BIN"
    exit 1
fi

if [ ! -f "$FFMPEG_BIN" ]; then
    log_warn "ffmpeg not found at $FFMPEG_BIN; WebM transcription may fail"
fi

# Target channels (default both, or specify one as arg)
CHANNELS=("Henry 的慢思考" "老厉害")
if [ $# -gt 0 ]; then
    CHANNELS=("$1")
fi

total_transcribed=0

for CHANNEL in "${CHANNELS[@]}"; do
    CHANNEL_DIR="$BASE_DIR/$CHANNEL"

    if [ ! -d "$CHANNEL_DIR" ]; then
        log_error "Channel directory not found: $CHANNEL_DIR"
        continue
    fi

    log_info "Processing channel: $CHANNEL"
    cd "$CHANNEL_DIR"

    transcribed=0

    # Find all video files that lack both .vtt and .txt
    # Use null terminator to handle filenames with spaces correctly
    while IFS= read -r -d '' video_file; do
        # Remove leading ./
        video_file="${video_file#./}"

        # Extract base name (remove extension)
        base="${video_file%.*}"

        # Check if transcript exists (either .vtt or .txt)
        if [ -f "$base.vtt" ] || [ -f "$base.txt" ]; then
            continue
        fi

        log_info "Transcribing: $video_file"

        # Handle WebM files: extract audio first
        if [[ "$video_file" == *.webm ]]; then
            audio_temp="/tmp/${base}_audio.wav"
            log_info "  Extracting audio from WebM..."
            $FFMPEG_BIN -i "$video_file" -ar 16000 -ac 1 -c:a pcm_s16le "$audio_temp" -loglevel quiet 2>&1 || {
                log_error "  Failed to extract audio from $video_file"
                continue
            }

            # Transcribe from extracted audio, let Whisper output to current dir
            $WHISPER_BIN "$audio_temp" \
                --model base \
                --language zh \
                --output_format vtt \
                2>&1 | grep -v "^$" >> "$CHANNEL_DIR/transcribe_detail.log" || {
                log_error "  Whisper failed for $video_file"
                rm -f "$audio_temp"
                continue
            }

            # Move the output file to match expected name
            if [ -f "${audio_temp%.*}.vtt" ]; then
                mv "${audio_temp%.*}.vtt" "$base.vtt"
            fi
            rm -f "$audio_temp"
        else
            # MP4: transcribe directly
            $WHISPER_BIN "$video_file" \
                --model base \
                --language zh \
                --output_format vtt \
                2>&1 | grep -v "^$" >> "$CHANNEL_DIR/transcribe_detail.log" || {
                log_error "  Whisper failed for $video_file"
                continue
            }
        fi

        # Check if VTT was actually created
        if [ ! -f "$base.vtt" ]; then
            log_error "  VTT file not found after transcription: $base.vtt"
            continue
        fi

        log_info "  ✓ VTT created"
        transcribed=$((transcribed + 1))
    done < <(find . -maxdepth 1 \( -name "*.mp4" -o -name "*.webm" \) -type f -print0)

    # Convert all VTT to TXT
    if [ -f "$VTT_CONVERTER" ]; then
        log_info "Converting VTT → TXT..."
        python3 "$VTT_CONVERTER" "$CHANNEL" 2>/dev/null || true
    fi

    log_info "Channel $CHANNEL: $transcribed new transcriptions"
    total_transcribed=$((total_transcribed + transcribed))
done

log_info "Total transcriptions: $total_transcribed"
