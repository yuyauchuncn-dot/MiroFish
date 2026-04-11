#!/bin/bash
# Monitor transcription and download progress

BASE_DIR="'$(dirname "${BASH_SOURCE[0]}")/../../..'/data/raw/media/youtube_downloads"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 YouTube 转录管道 — 实时进度"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Transcription status
echo ""
echo "📝 转录状态:"
if pgrep -q -f "transcribe_all.sh"; then
    echo "  ✓ Whisper 转录进程: 运行中"
    tail -5 "$BASE_DIR/transcribe.log" | sed 's/^/    /'
else
    echo "  ⊗ Whisper 转录进程: 已停止"
fi

# Download status
echo ""
echo "⬇️ 下载状态:"
if pgrep -q -f "download_youtube_channel.sh"; then
    echo "  ✓ 频道下载进程: 运行中"
    tail -5 "$BASE_DIR/download.log" | sed 's/^/    /'
else
    echo "  ⊗ 频道下载进程: 已停止"
fi

# Coverage status
echo ""
echo "📂 转录覆盖率:"
cd "$BASE_DIR/Henry 的慢思考"
mp4_count=$(ls -1 *.mp4 2>/dev/null | wc -l)
txt_count=$(ls -1 *.txt 2>/dev/null | wc -l)
coverage=$((txt_count * 100 / mp4_count))
printf "  Henry 的慢思考: %2d/%2d (%3d%%)\n" "$txt_count" "$mp4_count" "$coverage"

cd "$BASE_DIR/老厉害"
video_count=$(ls -1 *.mp4 *.webm 2>/dev/null | wc -l)
txt_count=$(ls -1 *.txt 2>/dev/null | wc -l)
coverage=$((txt_count * 100 / video_count))
printf "  老厉害:       %2d/%2d (%3d%%)\n" "$txt_count" "$video_count" "$coverage"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
