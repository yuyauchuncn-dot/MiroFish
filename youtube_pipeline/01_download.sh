#!/bin/bash
# MiroFish 流水线：第 1 步 - 下载视频或检查本地文件
# 接受：YouTube URL 或本地视频路径
# 输出：/tmp/mirofish_step.env (VIDEO_PATH, VIDEO_ID, CHANNEL)

set -e

# 定位 monorepo 根目录（youtube_pipeline -> MiroFish -> monorepo）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

YOUTUBE_DIR="$MONO_ROOT/data/raw/media/youtube_downloads"
ARCHIVE_FILE="$YOUTUBE_DIR/download_archive.txt"
COOKIES_FILE="$YOUTUBE_DIR/cookies.txt"
STEP_ENV="/tmp/mirofish_step.env"

# 清空旧的 step 文件
rm -f "$STEP_ENV"

# 检测 --v4 标志
USE_V4="false"
for arg in "$@"; do
    if [ "$arg" = "--v4" ]; then
        USE_V4="true"
        break
    fi
done

if [ $# -lt 1 ]; then
    echo "❌ 用法：$0 <youtube_url_or_local_path>"
    echo "   例子（URL）：$0 'https://www.youtube.com/watch?v=dXXXXXXXXXX'"
    echo "   例子（本地）：$0 '/path/to/video.mp4'"
    exit 1
fi

INPUT="$1"

# 判断是否为本地文件路径（以 / 或 ./ 开头）
if [[ "$INPUT" == /* ]] || [[ "$INPUT" == ./* ]]; then
    # === 本地文件路径 ===
    # 处理包含特殊字符的路径
    INPUT_DIR="$(cd "$(dirname "$INPUT")" && pwd)"
    INPUT_FILE="$(basename "$INPUT")"
    VIDEO_PATH="$INPUT_DIR/$INPUT_FILE"

    if [ ! -f "$VIDEO_PATH" ]; then
        echo "❌ 本地文件不存在：$VIDEO_PATH"
        exit 1
    fi

    echo "📁 使用本地文件：$VIDEO_PATH"

    # 从文件名提取 video_id (格式：... [VIDEO_ID].mp4)
    FILENAME=$(basename "$VIDEO_PATH")
    STEM="${FILENAME%.*}"

    if [[ "$STEM" =~ \[([^\]]+)\]$ ]]; then
        VIDEO_ID="${BASH_REMATCH[1]}"
    else
        echo "❌ 无法从文件名提取 video_id。期望格式：... [VIDEO_ID].mp4"
        exit 1
    fi

    # 推断频道（从父目录名）
    CHANNEL=$(basename "$(dirname "$VIDEO_PATH")")

    echo "🎯 Video ID：$VIDEO_ID"
    echo "📂 频道：$CHANNEL"

    # 保存到环境文件
    cat > "$STEP_ENV" << EOF
VIDEO_PATH=$VIDEO_PATH
VIDEO_ID=$VIDEO_ID
CHANNEL=$CHANNEL
USE_V4=$USE_V4
EOF

    echo "✅ 本地文件已准备"
    exit 0
fi

# === YouTube URL ===
echo "🌐 识别为 YouTube URL：$INPUT"

# 提取 video_id 从 URL
if [[ "$INPUT" =~ v=([a-zA-Z0-9_-]+) ]]; then
    VIDEO_ID="${BASH_REMATCH[1]}"
elif [[ "$INPUT" =~ youtu.be/([a-zA-Z0-9_-]+) ]]; then
    VIDEO_ID="${BASH_REMATCH[1]}"
else
    echo "❌ 无法从 URL 提取 video_id：$INPUT"
    exit 1
fi

echo "🎯 Video ID：$VIDEO_ID"

# 检查是否已下载过（在 archive 中）
if [ -f "$ARCHIVE_FILE" ]; then
    if grep -q "youtube $VIDEO_ID" "$ARCHIVE_FILE"; then
        echo "⚠️  视频已在 archive 中，尝试寻找本地文件..."
        # 搜索本地文件
        FOUND_FILE=$(find "$YOUTUBE_DIR" -name "*$VIDEO_ID*.mp4" 2>/dev/null | head -1 || true)
        if [ -n "$FOUND_FILE" ]; then
            echo "✅ 找到本地文件：$FOUND_FILE"
            CHANNEL=$(basename "$(dirname "$FOUND_FILE")")
            cat > "$STEP_ENV" << EOF
VIDEO_PATH=$FOUND_FILE
VIDEO_ID=$VIDEO_ID
CHANNEL=$CHANNEL
EOF
            exit 0
        fi
    fi
fi

# 下载视频
echo "📥 正在下载视频..."

# 推断频道（简单策略：从 URL 获取频道名，或使用默认）
# 这里使用较通用的方法：让 yt-dlp 下载到根目录，然后根据内容推断
TEMP_DIR="$YOUTUBE_DIR/temp_download"
mkdir -p "$TEMP_DIR"

# 构建 yt-dlp 命令
YT_DLP_CMD="yt-dlp"
[ -f "$COOKIES_FILE" ] && YT_DLP_CMD="$YT_DLP_CMD --cookies $COOKIES_FILE"

# 下载
$YT_DLP_CMD \
    --ignore-errors \
    --download-archive "$ARCHIVE_FILE" \
    --write-auto-sub \
    --sub-lang "zh-CN,zh-Hans,zh,en" \
    --sub-format "vtt" \
    --format "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/bestvideo+bestaudio/best" \
    --merge-output-format mp4 \
    -o "$TEMP_DIR/%(upload_date)s - %(title)s [%(id)s].%(ext)s" \
    "$INPUT" || {
    echo "❌ yt-dlp 下载失败"
    exit 1
}

# 在临时目录中查找下载的视频
DOWNLOADED_FILE=$(find "$TEMP_DIR" -name "*$VIDEO_ID*.mp4" 2>/dev/null | head -1 || true)

if [ -z "$DOWNLOADED_FILE" ]; then
    echo "❌ 下载成功但找不到视频文件"
    exit 1
fi

echo "✅ 视频下载完成：$DOWNLOADED_FILE"

# 自动获取频道名称
echo "📺 获取频道信息..."

# 使用 yt-dlp 获取频道名称（优先使用 uploader，因为某些视频 channel 返回 NA）
CHANNEL=$(yt-dlp --flat-playlist --print "uploader" "$INPUT" 2>/dev/null | head -1 | tr -d '\n')

# 如果获取失败，尝试备用方法
if [ -z "$CHANNEL" ] || [ "$CHANNEL" = "NA" ]; then
    # 尝试从 URL 提取频道名（@channel_name 格式）
    if [[ "$INPUT" =~ /@([^/?\&]+) ]]; then
        CHANNEL_URL="${BASH_REMATCH[1]}"
        # 使用 Python 进行 URL 解码
        CHANNEL=$(python3 -c "import urllib.parse; print(urllib.parse.unquote('$CHANNEL_URL'))" 2>/dev/null || echo "$CHANNEL_URL")
    else
        CHANNEL="未分类"
    fi
fi

echo "📂 频道：$CHANNEL"

# 移到频道目录
CHANNEL_DIR="$YOUTUBE_DIR/$CHANNEL"
mkdir -p "$CHANNEL_DIR"
mv "$DOWNLOADED_FILE" "$CHANNEL_DIR/" || {
    echo "⚠️  无法移动文件到频道目录，将保存在：$TEMP_DIR"
    CHANNEL_DIR="$TEMP_DIR"
}

VIDEO_PATH="$CHANNEL_DIR/$(basename "$DOWNLOADED_FILE")"

echo "📁 视频已保存：$VIDEO_PATH"

# 清理临时目录
rmdir "$TEMP_DIR" 2>/dev/null || true

# 保存到环境文件
cat > "$STEP_ENV" << EOF
VIDEO_PATH=$VIDEO_PATH
VIDEO_ID=$VIDEO_ID
CHANNEL=$CHANNEL
EOF

echo "✅ 下载完成"
